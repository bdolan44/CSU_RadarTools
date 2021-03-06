# -*- coding: utf-8 -*-
"""
Brenda Dolan's HID code ported from IDL.

Brody Fuchs, CSU, Sept 2014
brfuchs@atmos.colostate.edu

(apparently originally from Kyle Wiens)

Modifications by Timothy Lang
tjlangoc@gmail.com
"""

from __future__ import division
from __future__ import absolute_import
from __future__ import print_function

import numpy as np
from .beta_functions import get_mbf_sets_summer
from .beta_functions import get_mbf_sets_winter, CSV_DIR
from .calc_kdp_ray_fir import hid_beta_f

from .csu_t_traps import get_hid_traps
from .csu_fhc_melt import melting_layer
from .csu_fhc_winter import csu_fhc_winter


DEFAULT_WEIGHTS = {'DZ': 1.5, 'DR': 0.8, 'KD': 1.0, 'RH': 0.8, 'LD': 0.5,
                   'T': 0.4}


def hid_beta(x_arr, a, b, m):
    """Beta function calculator"""
    return 1.0/(1.0 + (((x_arr - m)/a)**2)**b)


###Add the ability to run the winter HID
"""
csu_fhc_winter.py

Brenda Dolan CSU, October 2018
bdolan@atmos.colostate.edu

Porting over Elizabeth Thompsons's HID code from IDL
(Based on Thompson et al. 2014)
(Also based on Dolan and Rutledge, 2009)

Thompson, E. J., Rutledge, S. A., Dolan, B., Chandrasekar, V.,
& Cheong, B. L. (2014). A dual-polarization radar hydrometeor classification
algorithm for winter precipitation. Journal of Atmospheric and Oceanic
Technology, 31(7), 1457-1481.


Input measurands (if not None, all must match in shape/size):

These should be masked arrays. For the winter HCA, Zdr, Kdp and rho are necessary inputs.
dz = Input reflectivity scalar/array
zdr = Input differential reflectivity scalar/array
ldr = Input linear depolarization ratio scalar/array
kdp = Input specific differential phase scalar/array
rho = Input correlation coefficient scalar/array
sn = Input signal to noise ratio scalar/array

Flags:
method: 'linear' scoring will multiply each variable by it's weight and sum the results.
        'hybrid' will multiply the score of reflectivity and temperature by the sum of the
                other variables times their weights.
sn_thresh: Signal to noise threshold to use to find good data.
minRH: THe minimum RhoHV to find good data.
expected_ML: The height of the assumed melting layer. This is used to determine how correct
        the radar-derived melting layer is.
band: determines the beta functions to use. Currently available: S, C, X
nsect: Determines the number of sectors to divide a PPI or grid into in order to find
        non-concentric bright bands.
azimuths: The azimuths of the PPI used in the melting layer detection.
scan_type: Pass the melting layer algorithm the scan type to improve it's detection ability 
        AVailable types are: ppi, rhi, and grid
heights: Height of the radar data.
verbose: How much is printed out relative to what the program is doing.
return_scores: Flag to return all of the information about each algorithm that goes into 
        the cold-season HCA.
fdir: Directory containing the Membership function definitions.        
    
returned data:
    Winter HCA categories
    
    Cateories:
    0  = Unclassified
    1  = Ice Crystals
    2  = Plates
    3  = Dendrites
    4  = Aggregates
    5  = Wet Snow
    6  = Frozen precip
    7  = Rain

    if return_scores:
        hca and scores are returned. Both are dictionaries containing the results of
        each step of the HCA including the melting layer, cold and warm logic.

"""

def run_winter(dz=None, zdr=None, rho=None, kdp=None, ldr=None, sn=None,
               T=None, use_temp=False, band='S', method='linear', sn_thresh=5,
               expected_ML=4.0, nsect=36, return_scores=False, azimuths=None,
               verbose=True, minRH=0.5, scan_type='ppi', heights=None,
               fdir=CSV_DIR):

    # The first step is to find the wet snow and the melting layer.

    meltlev, melt_z, fh, scores_ML = melting_layer(
        dz=dz, zdr=zdr, kdp=kdp, rho=rho, sn=sn, heights=heights,
        scan_type=scan_type, verbose=verbose, band=band,
        fdir=fdir, azimuths=azimuths, expected_ML=expected_ML, minRH=minRH,
        sn_thresh=sn_thresh, nsect=nsect)

    # Step 2 is to run the warm layer HID.
    # Using csu_fhc_winter and warm == True

    scores_warm = csu_fhc_winter(
        dz=dz, zdr=zdr, rho=None, kdp=kdp, use_temp=True, T=T, band='C',
        warm=True, verbose=verbose, fdir=fdir)
    fhwarm = np.argmax(scores_warm, axis=0) + 1
    # Now reset the fhwarm values to correspond to
    # 6 - Frozen
    # 7 - Rain
    fhwarm[fhwarm == 1] = 6
    fhwarm[fhwarm == 2] = 7

    scores_cold = csu_fhc_winter(dz=dz, zdr=zdr, rho=None, kdp=kdp,
                                 use_temp=True, T=T, band='C', warm=False,
                                 verbose=verbose, fdir=fdir)

    fhcold = np.argmax(scores_cold, axis=0) + 1

    # Now reset the fh values to correspond to
    # 5 - Wet Snow
    whgd = np.where(fh == 2)
    fh[whgd] = 5

    winter_hca = np.zeros_like(fh) - 1
    # Now combine them using the melting level idea.
    winter_hca[meltlev == 0] = fhwarm[meltlev == 0]
    winter_hca[meltlev == 2] = fhcold[meltlev == 2]
    if scan_type == 'grid':
        if verbose:
            print('Note: Things get weird at the melting level in a gridded file.')
        winter_hca[meltlev==1] = fhcold[meltlev==1]

    # whbad = np.where(fh == -1)
    whmelt = np.where(fh == 5)
    winter_hca[whmelt] = 5
    winter_hca[fh == -1] = -1
    winter_hca[fh == 0] = -1

    # Filter out where there is no pol data.
    # rhfill = rho.filled(fill_value = np.nan)
    # whbad = np.where(np.isnan(rhfill))
    # winter_hca[whbad] = -1

    if return_scores:
        scores = {'ML': scores_ML, 'warm': scores_warm, 'cold': scores_cold}
        hca = {'ML': fh, 'warm': fhwarm, 'cold': fhcold}
        return winter_hca, scores, hca
    else:
        return winter_hca




def csu_fhc_summer(use_temp=True, weights=DEFAULT_WEIGHTS, method='hybrid',
                   dz=None, zdr=None, ldr=None, kdp=None, rho=None, T=None,
                   verbose=False, plot_flag=False, use_trap=False,n_types=10, temp_factor=1,
                   band='S',return_scores=False):
    """
    Does FHC for warm-season precip.

    Arguments:
    use_temp = Set to False to not use T in HID
    weights = Dict that contains relative weights for every variable; see
              DEFAULT_WEIGHTS for expected stucture
    method = Currently support 'hybrid' or 'linear' methods; hybrid preferred unless using
            use_trap
    verbose = Set to True to get text updates
    plot_flag = Flag to turn on optional beta function plots
    band = 'X', 'C', or 'S'
    temp_factor = Factor to modify depth of T effects; > 1 will broaden the
                  slopes of T MBFs
    use_trap: The option to use trapezoidal membership functions for temperature. This
            allows for penalties in temperatures that are not possible for a given type.
            If this flag is used, the 'linear' method can produce better results.
    n_types = Number of hydrometeor species
    verbose = Set to True to get text updates

    Input measurands (if not None, all must match in shape/size):
    dz = Input reflectivity scalar/array
    zdr = Input reflectivity scalar/array
    ldr = Input reflectivity scalar/array
    kdp = Input reflectivity scalar/array
    rho = Input reflectivity scalar/array
    T = Input temperature scalar/array

    Returns:
        HID type number

    HID types:           Species #:
    -------------------------------
    Drizzle                  1
    Rain                     2
    Ice Crystals             3
    Aggregates               4
    Wet Snow                 5
    Vertical Ice             6
    Low-Density Graupel      7
    High-Density Graupel     8
    Hail                     9
    Big Drops                10

    if return_scores == True:
        scores = Input array + addtl dimension containing scores for each HID species
        
        This can be used to look at the relative scores of 2nd and 3rd order types.


    """

    if dz is None:
        print('FHC fail, no reflectivity field')
        return None
    if T is None:
        use_temp = False

    # Populate fhc_vars and radar_data based on what was passed to function
    radar_data, fhc_vars, shp, sz = \
        _populate_vars(dz, zdr, kdp, rho, ldr, T, verbose)

    # Now grab the membership beta function parameters
    mbf_sets = get_mbf_sets_summer(
        use_temp=use_temp, plot_flag=plot_flag, n_types=n_types,
        temp_factor=temp_factor, band=band, verbose=verbose)
    sets = _convert_mbf_sets(mbf_sets)

    # Check for presence of polarimetric variables
    pol_flag = _get_pol_flag(fhc_vars)

    #Check to see if user wants to use trapazoidal temperature functions
    if use_trap:
        if verbose:
            print('Using trapazoidal functions')
        trap_flag = True
    else:
        if verbose:
            print('Using beta functions')
        trap_flag = False

    # Check for presence of temperature
    if use_temp:
        if verbose:
            print('Using T in FHC')
    else:
        fhc_vars['T'] = 0
        if verbose:
            print('Not using T in FHC')

    # Get weighted sums
    weight_sum, varlist = _get_weight_sum(fhc_vars, weights, method, verbose)
    if weight_sum is None:
        return None

    # Now loop over every hydrometeor class
    test_list = _get_test_list(fhc_vars, weights, radar_data, sets, varlist,
                               weight_sum, pol_flag, trap_flag,use_temp, method, sz)
    if test_list is None:
        return None

    # Finish up
    mu = np.array(test_list)
    shp = np.concatenate([[n_types], shp])
    if verbose:
        print(mu.shape)
        print('mu max: ', mu.max())
    # return mu but make sure the shape is an int array
    #return mu.reshape(shp.astype(np.int32))
    
    
    if return_scores:
        return mu.reshape(shp.astype(np.int32))
    else:
        hid = np.argmax(mu.reshape(shp.astype(np.int32)), axis=0) + 1
        return hid


##########################
# Private Functions Below#
##########################


def _convert_mbf_sets(mbf_sets):
    """Gets mbf_sets dict into form that matches labels used in csu_fhc"""
    sets = {}
    sets['DZ'] = mbf_sets['Zh_set']
    sets['DR'] = mbf_sets['Zdr_set']
    sets['KD'] = mbf_sets['Kdp_set']
    sets['LD'] = mbf_sets['LDR_set']
    sets['RH'] = mbf_sets['rho_set']
    sets['T'] = mbf_sets['T_set']
    return sets


def _get_pol_flag(fhc_vars):
    """Check for presence of polarimetric variables"""
    if fhc_vars['DR'] or fhc_vars['KD'] or fhc_vars['LD'] or fhc_vars['RH']:
        pol_flag = True
    else:
        pol_flag = False
    return pol_flag


def _populate_vars(dz, zdr, kdp, rho, ldr, T, verbose):

    """
    Check for presence of each var, and update dicts as needed.
    Flattens multi-dimensional arrays to optimize processing.
    The output array from csu_fhc_summer() will be re-dimensionalized later.
    """
    varlist = [dz, zdr, kdp, rho, ldr, T]
    keylist = ['DZ', 'DR', 'KD', 'RH', 'LD', 'T']
    fhc_vars = {}
    radar_data = {}
    for i, key in enumerate(keylist):
        var = varlist[i]
        if var is not None:
            if key == 'DZ':
                shp = np.shape(var)
                sz = np.size(var)
            if np.ndim(var) > 1:
                radar_data[key] = np.array(var).ravel().astype('float32')
            elif np.ndim(var) == 1:
                radar_data[key] = np.array(var).astype('float32')
            else:
                radar_data[key] = np.array([var]).astype('float32')
            fhc_vars[key] = 1
        else:
            fhc_vars[key] = 0
    if verbose:
        print('USING VARIABLES: ', fhc_vars)
    return radar_data, fhc_vars, shp, sz


def _get_weight_sum(fhc_vars, weights, method, verbose):
    """Gets sum of weights and varlist used, which depend on method"""
    if 'hybrid' in method:
        if verbose:
            print('Using hybrid HID method. Pol vars weighted,',
                  'Z and T (if used) are multiplied')
        varlist = ['DR', 'KD', 'RH', 'LD']
    elif 'linear' in method:
        if verbose:
            print('NOT using hybrid, all variables treated as weighted sum')
        varlist = ['DR', 'KD', 'RH', 'LD', 'T', 'DZ']
    else:
        print('No weighting method defined, use hybrid or linear')
        return None, None
    weight_sum = np.sum(np.array([fhc_vars[key]*weights[key]
                                 for key in varlist]))
    if verbose:
        print('weight_sum: ', weight_sum)
    return weight_sum, varlist


def _calculate_test(fhc_vars, weights, radar_data, sets,
                    varlist, weight_sum, c, sz):
    """Loop over every var to get initial value for each HID species 'test'"""
#    test = (np.sum(np.array([fhc_vars[key] * weights[key] *
#                            hid_beta(radar_data[key], sets[key]['a'][c],
#                            sets[key]['b'][c], sets[key]['m'][c])
    test = (np.sum(np.array([fhc_vars[key] * weights[key] *
                            hid_beta_f(sz, radar_data[key], sets[key]['a'][c],
                            sets[key]['b'][c], sets[key]['m'][c])
            for key in varlist if key in radar_data.keys()]),
            axis=0))/weight_sum
    return test


def _calculate_test_trap(fhc_vars, weights, radar_data, sets,
                    varlist, weight_sum, c, sz):
    """Loop over every var to get initial value for each HID species 'test'"""
    ##Add here the option to call the trapazoidal temperauter functions.

    b_val = []
    for key in varlist :
        if key in radar_data.keys():
            if key == 'T':
                #print('Getting T trapazoids!')
                tst  = (get_hid_traps(c,radar_data[key]))
                #print(np.shape(tst))
                b_val.append(tst)
                
            else:
                tst =(fhc_vars[key]*weights[key]*hid_beta_f(sz,radar_data[key],sets[key]['a'][c],
                        sets[key]['b'][c],sets[key]['m'][c]))
                #print(np.shape(tst),type(b_val))
                b_val.append(tst)
    #             beta.append((np.array([fhc_vars[key] * weights[key] *
    #                             hid_beta_f(sz, radar_data[key], sets[key]['a'][c],
    #                             sets[key]['b'][c], sets[key]['m'][c])
    #             for key in varlist if key in radar_data.keys()]),
    #             axis=0)))
    test = (np.sum(np.array(b_val),axis=0)/weight_sum)
    return test


def _get_test_list(fhc_vars, weights, radar_data, sets, varlist, weight_sum,
                   pol_flag,trap_flag, use_temp, method, sz):
    """
    Master loop to compute HID values for each species ('test' & 'test_list').
    Depending on method used, approach is modfied.
    Currently disabling testing as it gets spoofed by bad data. Letting the
    calculations continue then mask out the bad data using other methods.
    TO DO: Change poor naming scheme for variables 'test' and 'test_list']
    """
    # TJL - Check order of if statements
    test_list = []
    for c in range(len(sets['DZ']['m'])):
        if 'hybrid' in method:  # Hybrid emphasizes Z and T extra HARD
            if pol_flag:
                #Here use the trapazoidal temperatuer functions instead of beta functions
                if trap_flag:
                    test = _calculate_test_trap(fhc_vars, weights, radar_data, sets,
                                           varlist, weight_sum, c, sz)
                else:
                    test = _calculate_test(fhc_vars, weights, radar_data, sets,
                                           varlist, weight_sum, c, sz)

                # if test.max() > 1:  # Max of test should never be > 1
                #     print 'Fail loc 1, test.max() =', test.max()
                #     return None
            if use_temp:
                if pol_flag:
                    # *= multiplies by new value and stores in test
                    test *= hid_beta_f(sz, radar_data['T'], sets['T']['a'][c],
                                       sets['T']['b'][c], sets['T']['m'][c])
                    # print 'in loc 2'
                    # if test.max() > 1: #Maximum of test should never be > 1
                    #     print 'Fail loc 2, test.max() =', test.max()
                    #     return None
                else:
                    test = hid_beta_f(sz, radar_data['T'], sets['T']['a'][c],
                                      sets['T']['b'][c], sets['T']['m'][c])
            if fhc_vars['DZ']:
                if pol_flag or use_temp:
                    test *= hid_beta_f(
                        sz, radar_data['DZ'], sets['DZ']['a'][c],
                        sets['DZ']['b'][c], sets['DZ']['m'][c])
                    # if test.max() > 1:  # Max of test should never be > 1
                    #     print 'Fail loc 3, test.max() =', test.max()
                    #     return None
                else:
                    test = hid_beta_f(sz, radar_data['DZ'], sets['DZ']['a'][c],
                                      sets['DZ']['b'][c], sets['DZ']['m'][c])
        elif 'linear' in method:  # Just a giant weighted sum
            if pol_flag:
                if trap_flag:
                    test = _calculate_test_trap(fhc_vars, weights, radar_data, sets,
                                           varlist, weight_sum, c, sz)
                else:
                    test = _calculate_test(fhc_vars, weights, radar_data, sets,
                                           varlist, weight_sum, c, sz)
                
        test_list.append(test)
    return test_list
