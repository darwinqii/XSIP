from nei_beam_parameters import *
from near_edge_imaging import *
import re
import inspect
from datetime import datetime
import copy
import math_physics as mp
import os

os.chdir(os.path.dirname(mp.__file__))  # Set Current Working Directory to the spectral_KES module directory


def nei(materials='', data_path='', save_path='', algorithm='sKES_equation', multislice=True,
        slice=0, n_proj=900, ct=False, side_width=0,
        e_range=0, lowpass=False, use_torch=True, use_file=True, arrangement_type='file',
        fix_vertical_motion=False, reconstruction=None, ct_center=0, snr=False,
        save=True, clip=False, flip=False, width_factor=1.0,
        use_sm_data=False, use_measured_standard=False,
        fix_beam_motion_banding=True,  # todo: 1. Add optin in GUI; 2. Automatic determine whether to use it or not.
        use_weights=False, energy_weights=0, flat_gamma=1.0,
        put_dark_back=False, fix_detector_factor=0,
        fix_cross_over=False,
        Verbose=False):
    """
    Get beam_parameters.
    Get $\mu/\rho$ [n_materials, n_energies,n_horizontal_positions]
    Get $\mu t$ [n_projections,n_energies,n_horizontal_positions]
    Get $\rho t$ [n_material, n_projection,n_horizontal_positions]
    Get CT reconstruction [n_material,n_horizontal,n_horizontal]
    Get Signal to Noise Ratio
    :param materials: A `list` of `str` for the names of the materials. For example, ['K2SeO4', 'K2SeO3', 'Se-Meth', 'Water']
                      Or, a `str` for the materials file name. For example, 'se' for the 'se.txt' file in the '\MU\materials' folder.
    :param path: The main directory containing Flat, Dark, Edge, Tomo, etc...
    :param use_file:
    :param algorithm: The algorithm used to calculate $\rho t$. Options are:
                      'sKES_equation': Default option. A equation derived with least-square approach is used.
                                       Much faster than 'nnls'. [Ref: Ying Zhu,2012 Dissertation]
                      'nnls'         : A Non-Negative Least Square Regression will be performed with `scipy.optimize.nnls`.
    :param ct: If True, a piece of left and right side of projection image will be used to correct the air absorption
               from sample to detector.
    :param side_width: Used with param "ct". Define the width in pixel for air absorption correction
    :param n_proj: The number of projection images for one slice of CT imaging.
    :param multislice: If True, meaning the images in the "tomo" folder contain more than one slice of CT. The 'n_proj'
                       and 'slice' needs to be specified.
    :param slice: Which slice do we want to do the reconstruction.
    :param e_range: The energy range we want to use. Default 0, meaning the "energy_range" in "arrangement.dat" file
                    will be used as the energy range. If not 0, this will overwrite the energy range from "arrangement.dat".
    :param lowpass: Use a lowpass filter(gaussian) on the $\mu t$ from experiment. Default is False for now(20180905)
    :param use_torch: use Pytorch.tensor instead of numpy.array for matrix operations. Default True.
    :param snr: Calculate the signal to noise ratio. Default False.
    :param reconstruction: str (default None). Routine used for CT reconstruction after having the sinograms.
                           Routines available: 'idl','skimage'.
    :param ct_center: Specify the rotation center for CT reconstruction if needed. Default is 0.
    :param fix_vertical_motion: Todo.
    :param fix_cross_over: Todo.
    :param flat_gamma: Todo. May be not needed.
    :param Verbose: If True, some detail will show up when run the program. And some matplotlib plot window might pause
                    the program.
    :return: names
             beam_parameters.
             mu_rhos: $\mu/\rho$ [n_materials, n_energies,n_horizontal_positions]
             mu_t:    $\mu t$ [n_projections,n_energies,n_horizontal_positions]
             rho_t:   $\rho t$ [n_material, n_projection,n_horizontal_positions]
             recons:  CT reconstruction [n_material,n_horizontal,n_horizontal]
             snrs:    Signal to Noise Ratio
             mean_rhos: The mean values of $\rho$ in the target area in recon image.
    Todo: fix_skes_data_edges
    """

    #################   define materials       ######################
    # Workflow: Try to read in default settings from '\mu\materials\default.txt'.
    # If no default settings, ask for input, and then save it as default.
    ############## changed to file and GUI for materials input. Jun 18, 2019.
    # # if `materials` is not defined, ask for input now
    # if materials == '':
    #     materials = input('\nPlease input the names of the materials to investigate.\n'
    #                       'For example: K2SeO4 Se-Meth, Water\n'
    #                       'Or press Enter to skip\n')
    #     materials = re.findall(r"[\w'-]+", materials)

    if not type(materials) == list:
        materials = define_materials(materials_filename=materials)
        print('(nei) materials defined in GUI')

    ##############   get path for experiment data file and path to save result  ######
    if data_path == '':
        data_path = choose_path()
    data_path = Path(data_path)
    print("\n Data directory: ", str(data_path), end='\n')

    if save_path == '':  # if save_path is empty, automatically make one under data_path
        save_path = data_path / 'Save'
    save_path = Path(save_path)
    date = str(datetime.today().date())
    timelabel = str(datetime.now().time())[:8].replace(':', '-')
    # save_path = save_path + '\\' + date + '\\'+timelabel+'\\'
    save_path = save_path / date / timelabel
    # make the save_path directory if it doesn't exist.
    if not save_path.exists():
        os.makedirs(save_path)

    print('\n Save directory: ', str(save_path), end='\n\n')
    # start counting time
    start = time.time()

    ##############    print argument settings   ########################
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)
    print(' Argument settings:')
    for i in args:
        print("    %s = %s" % (i, values[i]))

    #############  get system setup info from arrangement.dat file ##########
    setup = nei_get_arrangement(data_path, save_path, arrangement_type=arrangement_type)
    detector = setup.detector

    # overwrite energy_range from arrangement file if needed
    if e_range != 0: setup.energy_range = e_range

    ########  get beam files: averaged flat, dark, and edge  ############
    print('\n(nei) Running "get_beam_files"')
    beam_files = get_beam_files(path=data_path, clip=clip, flip=flip, Verbose=Verbose)

    #################### Get beam_parameters #####################
    print('\n(nei) Running "nei_beam_parameters"')

    beam_parameters = nei_beam_parameters(beam_files=beam_files,
                                          setup=setup, detector=detector,
                                          fix_vertical_motion=fix_vertical_motion,
                                          clip=clip, Verbose=Verbose)

    ####################  Main calculation  #################################
    '''
    The following is the main calculation for Spectral Imaging / Energy Dispersive Xray Absorption Spectroscopy.
    
    - Get mu_rho values for every material at every y(energy),x position on the detector (in the image).
    - Calculate the $\mu t$ for every y position (representing energy) at every x position
        (representing horizontal position in the sample) in every projection image.
    - Calculate the $\rho t$ at every x(horizontal) position for every material.
    In theory, if there is only one material, we can solve the $\rho t$ with the information at one energy
    position, by $(\mu t)/(\mu/\rho)$. When we have 3 materials, we can solve it with 3 energy points.
    In reality, we have sometimes over 1000 energy points, so we use linear regression (or other algorithm)
    to solve the coefficient of every material.
    '''
    ##########  get murho values for every material at [y,x] position  ############
    print('\n(nei) Running "nei_determine_murhos"')
    gaussian_energy_width = beam_parameters.e_width * width_factor  # gaussian edge width in terms of energy
    exy = beam_parameters.exy
    mu_rhos = nei_determine_murhos(materials, exy, gaussian_energy_width=gaussian_energy_width,
                                   use_file=use_file, use_measured_standard=use_measured_standard)
    # dict to np.array. Save the names list as array index reference
    names = list(mu_rhos.keys())
    mu_rhos = np.array(list(mu_rhos.values()))

    #################### Todo: iterate through multi-slices   ###################
    # if multislice:
    #     path = Path(data_path)
    #     sub_dir = NeiSubDir(path)
    #     tomo_files_all = file_search(sub_dir.Tomo, '*tif') # this is only a list of file names
    #     n_tomo_files_all = len(tomo_files_all)
    #     if isinstance(slice, int): # if integer, process this single slice
    #         slices = [slice]
    #     elif isinstance(slice,list): # if list, process slices in the list
    #         slices = slice
    #     else:# if slice is "All" or something else but not an Integer or List, process for all slices
    #         slices = np.arange(n_tomo_files_all)
    #
    #     for s in slices:
    #####################    get tomo data               ########################
    print('\n(nei) Running "get_tomo_files"')
    tomo_data = get_tomo_files(data_path, multislice=multislice, slice=slice, n_proj=n_proj)

    ####################  calculate -ln(r)=  mu/rho * rho * t   #################
    print('\n(nei) Running "calculate_mut"')
    mu_t = calculate_mut(tomo_data, beam_parameters, lowpass=lowpass,
                         ct=ct, side_width=side_width)

    ####################  Todo: something to reduce artifact   ############

    ####################          calculate rho*t               #################
    beam = beam_parameters.beam
    print('\n(nei) Running "calculate_rhot"')
    rho_t = calculate_rhot(mu_rhos, mu_t, beam, names=names, algorithm=algorithm, use_torch=use_torch)
    if fix_beam_motion_banding:
        print('\n(beam_motion_banding_filter) Cleaning beam motion bandings. ')
        if rho_t.ndim==3:
            for i in range(rho_t.shape[0]):
                rho_t[i]=beam_motion_banding_filter(rho_t[i],padding=20)  # todo: Merge `padding` and `side_width`.
        elif rho_t.ndim==2:
            rho_t = beam_motion_banding_filter(rho_t, padding=20)
        else:
            raise ValueError('`rho_t` has invalid dimensions ')


    ####################   get signal to noise ratio if needed  #################
    snrs = 'To get Signal-to-Noise Ratio\nOption 1: Change the "snr" argument to"snr=True" when calling "nei()";' \
           '\nOption 2: Use the "near_edge_imaging.signal_noise_ratio" function.'
    if snr:
        print('\n(nei) Running "signal_noise_ratio"')
        snrs = signal_noise_ratio(mu_rhos, mu_t, rho_t, beam_parameters, tomo_data, use_torch)

    ####################   do CT reconstruction if needed  ######################
    if reconstruction:
        print('\n(nei) Running CT reconstruction with ' + reconstruction)
        pixel = setup.detector.pixel / 10  # change pixel unit to cm
        # Available reconstruction tools. Use the one specified by "reconstruction"
        recon_funcs = {'idl': idl_recon, 'skimage': skimage_recon}
        recons = recon_funcs[reconstruction](rho_t, pixel_size=pixel, center=ct_center)
        # mean_rhos = rho_in_ct(recons, names, save_path=save_path)  # todo: update rho_in_ct() function
        mean_rhos=""
        # plt.show()
    else:
        recons = 'To get CT Reconstruction Image\nOption 1: Change the "reconstruction" argument to"reconstruction=True" when calling "nei()";' \
                 '\nOption 2: Use the "near_edge_imaging.idl_ct()" function.'
        mean_rhos = ''
    ####################   Wrap up results and return  ###########################
    beam_parameters.setup = setup

    class Result:
        def __init__(self, names, beam_parameters, mu_rhos, mu_t, rho_t, snrs, recons, mean_rhos):
            self.names = names
            self.beam_parameters = beam_parameters
            self.mu_rhos = mu_rhos
            self.mu_t = mu_t
            self.rho_t = rho_t
            self.snrs = snrs
            self.recons = recons
            self.mean_rhos = mean_rhos

    print('\n(nei) Total running time for "nei":'
          '\n     ', round(time.time() - start, 2), 'seconds')
    result = Result(names, beam_parameters, mu_rhos, mu_t, rho_t, snrs, recons, mean_rhos)

    # (2019 Feb 15) Added the following line to free up some memory
    del names, beam_parameters, mu_rhos, mu_t, rho_t, snrs, recons, mean_rhos

    print('\n(nei) Saving results...')
    if save:
        # Note: Use copy.deepcopy(). Because the save_object function would transform the
        # structure of the input object into the form of nested dictionary.
        save_result(save_path, copy.deepcopy(result), args, values)

        # # # Note: do dict_to_object to transform the result back to class object (Added 2019 Feb 15)
        # save_result(save_path,result,args,values)
        # result = dict_to_class(result)
        print('      Results are saved at', str(save_path))
    else:  # data will not be saved, but parameter settings will still be saved.
        save_result(save_path, None, args, values)
        print('      Program parameters are saved at', str(save_path))

    return result


def get_mut(path=''):
    if path == '':
        path = Path(choose_path())
    elif type(path) == str:
        path = Path(path)
    else:
        pass
    beam_parameters = get_beam_parameters(path)
    tomo = get_tomo_files(path)
    mu_t = calculate_mut(tomo, beam_parameters)
    return mu_t


if __name__ == '__main__':
    # materials = ['Na2SeO4', 'Na2SeO3', 'Se-Meth', 'Water']
    # materials = ['SeO4', 'SeO3', 'Se-Meth', 'Water']
    # data_path = r'G:\Large Storage\XrayData\Pod_Tubes_CT 2_1 Slice'
    # multislice = True
    # slice_num = 0
    # n_proj = 900
    # side_width = 0
    # data = nei(materials=materials, data_path=data_path, multislice=multislice,
    #            slice=slice_num, n_proj=n_proj, save=True, use_torch=False)
    result = nei(materials=['I','Water'],
                 data_path=r'H:\1_PhD_data\2015-08-14-C2-SpectralData-Arash',
                 multislice=True,  # Whether the imaging data is from a multislice scan
                 slice=0,  # If `multislice==True`, provide the number of slice to analyze (starting from 0)
                 n_proj=900,  # The number of projection images per slice
                 ct=True,  # Whether this is a CT scan. If `True`, `side_width` will be used.
                 side_width=20,  # The number of pixels used on the side.
                 e_range=0,  # The interested energy range for analysis. `0` for all available energies.
                 lowpass=False,  # If `True`, apply a lowpass filter to reduce high frequency noise.
                 reconstruction='skimage',
                 save=True,  # Save the result or not (because the return result is usually large)?
                 Verbose=False)
