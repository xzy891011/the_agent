import app.tools.meanderpy.meanderpy as mp
import numpy as np
import yaml


def build_fluvial_model(yaml_path: str, image_path: str):
    params = []

    with open(yaml_path, 'r') as file:
        params = yaml.safe_load(file)

    nit = params['nit']  # number of iterations
    W = params['W']  # channel width (m)
    D = params['D']  # channel depth (m)
    depths = D * np.ones((nit,))  # channel depths for different iterations
    pad = params['pad']  # padding (number of nodepoints along centerline)
    deltas = params['deltas']  # sampling distance along centerline
    Cfs = params['Cfs_weight'] * np.ones((nit,))  # dimensionless Chezy friction factor
    crdist = params['crdist_weight'] * W  # threshold distance at which cutoffs occur
    kl = params['kl'] / (365 * 24 * 60 * 60.0)  # migration rate constant (m/s)
    kv = params['kv']  # vertical slope-dependent erosion rate constant (m/s)
    dt = params['dt'] * 365 * 24 * 60 * 60.0  # time step (s)
    dens = params['dens']  # density of water (kg/m3)
    saved_ts = params['saved_ts']  # which time steps will be saved
    n_bends = params['n_bends']  # approximate number of bends you want to model
    Sl = params['Sl']  # initial slope (matters more for submarine channels than rivers)
    t1 = params['t1']  # time step when incision starts
    t2 = params['t2']  # time step when lateral migration starts
    t3 = params['t3']  # time step when aggradation starts
    aggr_factor = params['aggr_factor']  # aggradation factor (m/s, about 0.18 m/year, it kicks in after t3)

    ch = mp.generate_initial_channel(W, depths[0], Sl, deltas, pad, n_bends)  # initialize channel
    chb = mp.ChannelBelt(channels=[ch], cutoffs=[], cl_times=[0.0], cutoff_times=[])  # create channel belt object

    chb.migrate(nit, saved_ts, deltas, pad, crdist, depths, Cfs, kl, kv, dt, dens, t1, t2, t3,
                aggr_factor)  # channel migration
    # fig1 = chb.plot('strat', 20, 60, chb.cl_times[-1], len(chb.channels))  # plotting
    # fig2 = chb.plot('morph', 20, 60, chb.cl_times[-1], len(chb.channels))
    # fig3 = chb.plot('age', 20, 60, chb.cl_times[-1], len(chb.channels))
    #
    # fig1.savefig(image_path + 'figure1.png', dpi=300, bbox_inches='tight')
    # fig2.savefig(image_path + 'figure2.png', dpi=300, bbox_inches='tight')
    # fig3.savefig(image_path + 'figure3.png', dpi=300, bbox_inches='tight')

    # build3d
    h_mud = params['h_mud'] * np.ones((len(chb.channels),))  # thickness of overbank deposit for each time step
    dx = params['dx']  # gridcell size in meters
    diff_scale = params['diff_scale'] * W / dx
    v_coarse = params[
        'v_coarse']  # deposition rate of coarse overbank sediment, in m/year (excluding times of no flooding)
    v_fine = params['v_fine']  # deposition rate of fine overbank sediment, in m/year (excluding times of no flooding)
    xmin = params['xmin']
    xmax = params['xmax']
    ymin = params['ymin']
    ymax = params['ymax']

    chb_3d, xmin, xmax, ymin, ymax, dists, zmaps = mp.build_3d_model(chb, 'fluvial',
                                                                     h_mud=h_mud, h=12.0, w=W,
                                                                     bth=0.0, dcr=10.0, dx=dx, delta_s=deltas, dt=dt,
                                                                     starttime=chb.cl_times[0],
                                                                     endtime=chb.cl_times[-1],
                                                                     diff_scale=diff_scale, v_fine=v_fine,
                                                                     v_coarse=v_coarse,
                                                                     xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)

    fig4, fig5, fig6 = chb_3d.plot_xsection(200, [[0.9, 0.9, 0], [0.5, 0.25, 0]], 4)
    #
    fig4.savefig(image_path + 'figure4.png', dpi=300, bbox_inches='tight')
    # fig5.savefig(image_path + 'figure5.png', dpi=300, bbox_inches='tight')
    # fig6.savefig(image_path + 'figure6.png', dpi=300, bbox_inches='tight')

    return f"状态：成功\n 备注：生成的河道图像保存在{image_path}/下"