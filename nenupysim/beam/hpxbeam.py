#! /usr/bin/python3
# -*- coding: utf-8 -*-


"""
    ************
    HEALPix Beam
    ************
"""


__author__ = 'Alan Loh'
__copyright__ = 'Copyright 2020, nenupy'
__credits__ = ['Alan Loh']
__maintainer__ = 'Alan'
__email__ = 'alan.loh@obspm.fr'
__status__ = 'Production'
__all__ = [
    'HpxBeam',
    'HpxABeam',
    'HpxDBeam'
]


from nenupysim.astro import HpxSky, wavelength
from nenupysim.beam import ma_antpos, ma_info, ma_pos
from nenupysim.instru import (
    desquint_elevation,
    analog_pointing,
    nenufar_ant_gain
)

import numpy as np
import numexpr as ne
from multiprocessing import Pool, sharedctypes
from healpy import ud_grade


# ============================================================= #
# ------------------- Parallel computation -------------------- #
# ============================================================= #
def _init(arr_r, arr_i, coeff, delay):
    """
    """
    global arr1
    global arr2
    global coef
    global darr
    arr1 = arr_r
    arr2 = arr_i
    coef = coeff
    darr = delay
    return


def fill_per_block(args):
    indices = args.astype(int)
    tmp_r = np.ctypeslib.as_array(arr1)
    tmp_i = np.ctypeslib.as_array(arr2)
    dd = darr[:, indices]
    beam_part = ne.evaluate('exp(coef*dd)')
    tmp_r[:, indices] = beam_part.real
    tmp_i[:, indices] = beam_part.imag
    return


def mp_expo(ncpus, coeff, delay):
    block_indices = np.array_split(
        np.arange(delay.shape[1]),
        ncpus
    )
    result_r = np.ctypeslib.as_ctypes(
        np.zeros_like(delay)
    )
    result_i = np.ctypeslib.as_ctypes(
        np.zeros_like(delay)
    )
    shared_r = sharedctypes.RawArray(
        result_r._type_,
        result_r
    )
    shared_i = sharedctypes.RawArray(
        result_i._type_,
        result_i
    )
    pool = Pool(
        processes=ncpus,
        initializer=_init,
        initargs=(shared_r, shared_i, coeff, delay)
    )
    res = pool.map(fill_per_block, (block_indices))
    result_r = np.ctypeslib.as_array(shared_r)
    result_i = np.ctypeslib.as_array(shared_i)
    return result_r + 1j * result_i
# ============================================================= #


# ============================================================= #
# ------------------------- HpxABeam -------------------------- #
# ============================================================= #
class HpxBeam(HpxSky):
    """
    """

    def __init__(self, resolution=1):
        super().__init__(
            resolution=resolution
        )

    # --------------------------------------------------------- #
    # --------------------- Getter/Setter --------------------- #
    

    # --------------------------------------------------------- #
    # ------------------------ Methods ------------------------ #
    def array_factor(self, az, el, antpos, freq):
        """
        """
        def get_phi(az, el, antpos):
            xyz_proj = np.array(
                [
                    np.cos(az) * np.cos(el),
                    np.sin(az) * np.cos(el),
                    np.sin(el)
                ]
            )
            antennas = np.matrix(antpos)
            phi = antennas * xyz_proj
            return phi

        # Compensate beam squint
        el = desquint_elevation(elevation=el).value
        # Real pointing
        az, el = analog_pointing(az, el)
        az = az.value
        el = el.value

        phi0 = get_phi(
            az=[np.radians(az)],
            el=[np.radians(el)],
            antpos=antpos
        )
        phi_grid = get_phi(
            az=self.ho_coords.az.rad,
            el=self.ho_coords.alt.rad,
            antpos=antpos
        )
        nt = ne.set_num_threads(ne._init_num_threads())
        delay = ne.evaluate('phi_grid-phi0')
        coeff = 2j * np.pi / wavelength(freq)
        
        if self.ncpus == 1:
            # Normal
            af = ne.evaluate('sum(exp(coeff*delay),axis=0)')
        else:
            # Multiproc
            af = np.sum(mp_expo(self.ncpus, coeff, delay), axis=0)

        return np.abs(af * af.conjugate())


    def plot(self):
        """
        """
        from nenupysim.astro import to_radec, ho_coord
        from healpy.visufunc import mollview, projplot
        # radec = to_radec(
        #     ho_coord(
        #         self.elana,
        #         self.azana,
        #         self.time)
        # )
        mollview(
            np.log10(self.skymap),
            #self.skymap,
            title='',
            cbar=False,
            #rot=(radec.ra.deg, radec.dec.deg, 0)
        )
        # projplot(
        #     radec.ra.deg,
        #     radec.dec.deg,
        #     marker='o',
        #     color='tab:red',
        #     lonlat=True
        #     )
        return

# ============================================================= #


# ============================================================= #
# ------------------------- HpxABeam -------------------------- #
# ============================================================= #
class HpxABeam(HpxBeam):
    """
    """

    def __init__(self, resolution=1, **kwargs):
        super().__init__(
            resolution=resolution
        )
        self._fill_attr(kwargs)

    # --------------------------------------------------------- #
    # --------------------- Getter/Setter --------------------- #
    

    # --------------------------------------------------------- #
    # ------------------------ Methods ------------------------ #
    def beam(self, **kwargs):
        """
        """
        self._fill_attr(kwargs)

        arrfac = self.array_factor(
            az=self.azana,
            el=self.elana,
            antpos=ma_antpos(
                rot=ma_info['rot'][ma_info['ma'] == self.ma][0]
            ),
            freq=self.freq
        )
        # Antenna Gain
        antgain = nenufar_ant_gain(
            freq=self.freq,
            polar=self.polar,
            nside=self.nside,
            time=self.time
        )[self._is_visible]

        # Make sure to have an empty skymap to begin with
        self.skymap[:] = 0.
        # Udpate the pixels that can be seen
        self.skymap[self._is_visible] = arrfac * antgain
        return


    # --------------------------------------------------------- #
    # ----------------------- Internal ------------------------ #
    def _fill_attr(self, kwargs):
        """
        """
        def_vals = {
            'ma': 0,
            'freq': 50,
            'azana': 180,
            'elana': 90,
            'polar': 'NW',
            'ncpus': 1,
            'time': None,
            **kwargs
        } 
        for key, val in def_vals.items():
            if hasattr(self, key) and (key not in kwargs.keys()):
                continue
            setattr(self, key, val)
        return
# ============================================================= #


# ============================================================= #
# ------------------------- HpxDBeam -------------------------- #
# ============================================================= #
class HpxDBeam(HpxBeam):
    """
    """

    def __init__(self, resolution=1, **kwargs):
        super().__init__(
            resolution=resolution
        )
        self._fill_attr(kwargs)

    # --------------------------------------------------------- #
    # --------------------- Getter/Setter --------------------- #

    # --------------------------------------------------------- #
    # ------------------------ Methods ------------------------ #
    def beam(self, **kwargs):
        """
        """
        self._fill_attr(kwargs)

        # Build the Mini-Array 'summed' response
        ana = HpxABeam(
            resolution=0.5 #self.resolution Fix it
        )
        abeams = {}
        for ma in self.ma:
            rot = ma_info['rot'][ma_info['ma'] == ma][0]
            if str(rot%60) not in abeams.keys():
                kwargs['ma'] = ma
                ana.beam(
                    **kwargs
                )
                abeams[str(rot%60)] = ud_grade(
                    ana.skymap,
                    nside_out=self.nside
                )[self._is_visible].copy()
            if not 'summa' in locals():
                summa = abeams[str(rot%60)]
            else:
                summa += abeams[str(rot%60)]

        arrfac = self.array_factor(
            az=self.azana,
            el=self.elana,
            antpos=ma_pos[np.isin(ma_info['ma'], self.ma)],
            freq=self.freq
        )

        beam = arrfac * summa

        # Make sure to have an empty skymap to begin with
        self.skymap[:] = 0.
        # Udpate the pixels that can be seen
        self.skymap[self._is_visible] = beam
        return


    # --------------------------------------------------------- #
    # ----------------------- Internal ------------------------ #
    def _fill_attr(self, kwargs):
        """
        """
        def_vals = {
            'ma': ma_info['ma'],
            'freq': 50,
            'azana': 180,
            'elana': 90,
            'azdig': 180,
            'eldig': 90,
            'polar': 'NW',
            'ncpus': 1,
            'time': None,
            **kwargs
        } 
        for key, val in def_vals.items():
            if hasattr(self, key) and (key not in kwargs.keys()):
                continue
            setattr(self, key, val)
        return
# ============================================================= #

