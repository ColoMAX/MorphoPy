import copy
import random
import networkx as nx
import numpy as np
import pandas as pd
import configparser as cp
import matplotlib.pyplot as plt
import seaborn as sns
from neurontree.utils import smooth_gaussian


def get_persistence(neurontree=None, f=None):
    """
    Creates the persistence barcode for the graph G. The algorithm is taken from
    _Quantifying topological invariants of neuronal morphologies_ from Lida Kanari et al
    (https://arxiv.org/abs/1603.08432).
    changed for use with networkx v2 (works also in old version: list(G.neighbors()))
    :return: pandas.DataFrame with entries node_id | birth | death . Where birth and death are defined in radial
        distance from soma.
    """

    # Initialization
    L = neurontree.get_tips()
    R = neurontree.get_root()
    G = neurontree.get_graph()
    D = dict(node_id=[], node_type=[], birth=[], death=[])  # holds persistence barcode
    v = dict()  # holds 'aging' function of visited nodes defined by f

    # active nodes
    A = list(copy.copy(L))

    if f is None:
        # radial distance function
        def f(G, u, v):
            n = G.node[u]['pos']
            r = G.node[v]['pos']

            return np.sqrt(np.dot(n - r, n - r))

    # set the initial value for leaf nodes
    for l in L:
        v[l] = f(G, l, R)

    while R not in A:
        for l in A:
            p = list(G.predecessors(l))[0]
            C = list(G.successors(p))

            # if all children are active
            if all(c in A for c in C):
                # choose randomly from the oldest children
                age = np.array([np.abs(v[c]) for c in C])
                indices = np.where(age == age[np.argmax(age)])[0]
                c_m = C[random.choice(indices)]

                A.append(p)

                for c_i in C:
                    A.remove(c_i)
                    if c_i != c_m:
                        D['node_id'].append(c_i)
                        D['node_type'].append(G.node[c_i]['type'])
                        D['birth'].append(v[c_i])
                        D['death'].append(f(G, p, R))
                v[p] = v[c_m]
    D['node_id'].append(R)
    D['node_type'].append(1)
    D['birth'].append(v[R])
    D['death'].append(f(G, R, R))
    return pd.DataFrame(D)

def compute_Morphometric_Statistics(neurontree=None):
    z = dict()
    z['branch_points'] = neurontree.get_branchpoints().size

    extend = neurontree.get_extend()
    z['width'] = extend[0]
    z['depth'] = extend[1]
    z['height'] = extend[2]

    tips = neurontree.get_tips()
    z['tips'] = tips.size

    root = neurontree.get_root()
    z['stems'] = len(neurontree.edges(root))

    z['total_length'] = np.sum(list(nx.get_edge_attributes(neurontree.get_graph(), 'path_length').values()))
    # get all radii
    radii = nx.get_node_attributes(neurontree.get_graph(), 'radius')
    # delete the soma
    radii.pop(neurontree.get_root())
    z['avg_thickness'] = np.mean(list(radii.values()))
    z['max_thickness'] = np.max(list(radii.values()))

    z['total_surface'] = np.sum(list(neurontree.get_surface().values()))
    z['total_volume'] = np.sum(list(neurontree.get_volume().values()))

    z['max_path_dist_to_soma'] = np.max(neurontree.get_distance_dist()[1])
    z['max_branch_order'] = np.max(list(neurontree.get_branch_order().values()))

    path_angles = []
    for p1 in neurontree.get_path_angles().items():
        if p1[1].values():
            path_angles += list(list(p1[1].values())[0].values())

    z['max_path_angle'] = np.percentile(path_angles, 99.5)
    z['min_path_angle'] = np.min(path_angles)
    z['median_path_angle'] = np.median(path_angles)

    R = neurontree.get_mst()
    segment_length = R.get_segment_length()
    terminal_segment_pl = [item[1] for item in segment_length.items() if item[0][1] in tips]
    intermediate_segment_pl = [item[1] for item in segment_length.items() if item[0][1] not in tips]

    z['max_segment_path_length'] = np.max(list(segment_length.values()))
    z['median_intermediate_segment_pl'] = np.median([0] + intermediate_segment_pl)
    z['median_terminal_segment_pl'] = np.median(terminal_segment_pl)

    tortuosity = [e[2]['path_length'] / e[2]['euclidean_dist'] for e in R.edges(data=True)]

    z['max_tortuosity'] = np.log(np.percentile(tortuosity, 99.5))
    z['min_tortuosity'] = np.log(np.min(tortuosity))
    z['median_tortuosity'] = np.log(np.median(tortuosity))

    branch_angles = R.get_branch_angles()
    z['max_branch_angle'] = np.max(branch_angles)
    z['min_branch_angle'] = np.min(branch_angles)
    z['mean_branch_angle'] = np.mean(branch_angles)

    # get maximal degree within data
    z['max_degree'] = np.max([item[1] for item in R.get_graph().out_degree() if item[0] != R.get_root()])

    # get tree asymmetry
    weights, psad = R.get_psad()
    if np.sum(list(weights.values())) != 0:
        z['tree_asymmetry'] = np.sum([weights[k] * psad[k] for k in psad.keys()]) / np.sum(list(weights.values()))
    else:
        z['tree_asymmetry'] = 0

    return pd.DataFrame.from_dict(z, orient='index')

def compute_Density_Maps(neurontree=None, conf=None):
    # get the resampled point could along each neurite at distance 1 micron.
    # pc is an array of 3D coordinates for each resampled node
    pc = neurontree.resample_nodes(d=1)

    # holds all density plots to return to user
    plots = []
    plt.figure()
    plt.scatter(pc[:, 0], pc[:, 2], s=1)
    sns.despine()
    plt.title('Density Map with resampled nodes')
    plots.append(plt)

    ###### PARAMETER ################
    # read from config if available
    if conf is not None:
        cfg = cp.ConfigParser()
        cfg.read(conf)

        min = np.array([cfg.getfloat("norm_bound", "r_min_x"),
                       cfg.getfloat("norm_bound", "r_min_y"),
                       cfg.getfloat("norm_bound", "r_min_z")])
        max = np.array([cfg.getfloat("norm_bound", "r_max_x"),
                       cfg.getfloat("norm_bound", "r_max_y"),
                       cfg.getfloat("norm_bound", "r_max_z")])
        r = dict(min=min, max=max)

        proj_axes = cfg.get("global", "proj_axes")
        n_bins = cfg.getint("global", "n_bins")
        normed = cfg.getboolean("global", "normed")
        smooth = cfg.getboolean("global", "smooth")
        sigma = cfg.getint("global", "sigma")
    else:
        # set default values if no config available:
        # r holds the normalization bounds
        r = dict(min=np.min(pc, axis=0), max=np.max(pc, axis=0))
        # which axes to project on
        proj_axes = '02'
        n_bins = 100
        normed = True
        smooth = False
        sigma = 1

    dim = len(proj_axes)

    ######## COMPUTATION ############
    # normalize point cloud
    pc = (pc - r['min']) / (r['max'] - r['min'])

    # holds the range for binning of the histogram. So far the cells are noramlized to be between max --> 1 and min --> 0
    # I can therefore know, that the point will lie between 0 and 1. However, the range could also be a parameter set
    # in the config file.
    range_ = [[-.1, 1.1]] * dim
    data = _project_data(proj_axes, pc)

    # compute histogram hence density map
    H_100, edges = np.histogramdd(data, bins=(n_bins,) * dim,
                                  range=range_, normed=normed)

    H_20, edges_20 = np.histogramdd(data, bins=(20,) * dim,
                                    range=range_, normed=normed)

    H_10, edges_10 = np.histogramdd(data, bins=(10,) * dim,
                                    range=range_, normed=normed)

    # perform smoothing
    if smooth:
        H_100 = smooth_gaussian(H_100, dim=dim, sigma=sigma)
        H_20 = smooth_gaussian(H_20, dim=dim, sigma=sigma)
        H_10 = smooth_gaussian(H_10, dim=dim, sigma=sigma)


    # plot maps and store in array
    plt.figure(figsize=(15, 5))
    plt.title('Histogram hence density map')

    plt.subplot(131)
    plt.imshow(H_100.T)
    plt.gca().invert_yaxis()
    plt.title('100 bins')

    plt.subplot(132)
    plt.imshow(H_20.T)
    plt.gca().invert_yaxis()
    plt.title('20 bins')

    plt.subplot(133)
    plt.imshow(H_10.T)
    plt.gca().invert_yaxis()
    plt.title('10 bins')
    plots.append(plt)



    for proj_axes, ax in [('0', 'x'), ('1', 'y'), ('2', 'z')]:

        plt.figure()
        plt.title('Histogram hence density map')
        dim = len(proj_axes)

        # holds the range for binning of the histogram. So far the cells are noramlized to be between max --> 1 and min --> 0
        # I can therefore know, that the point will lie between 0 and 1. However, the range could also be a parameter set
        # in the config file.
        range_ = [[-.1, 1.1]] * dim
        data = _project_data(proj_axes, pc)

        for k, n_bins in enumerate([100, 20], start=1):
            # compute histogram hence density map
            H, edges = np.histogramdd(data, bins=(n_bins,) * dim,
                                      range=range_, normed=normed)

            # perform smoothing
            if smooth:
                H = smooth_gaussian(H, dim=dim, sigma=sigma)

            plt.subplot(2, 2, k)
            plt.plot(H)
            sns.despine()
            plt.xlabel(ax)
            plt.title('%i bins' % n_bins)

        plt.suptitle('Projection onto the %s axis' % ax, weight='bold')
        plots.append(plt)

    return plots



def _project_data(proj_axes, data):
    """
        Helper function to project data onto the the axes defined in proj_axes.

        :param proj_axes:   str that holds the axes that are projected to as number, e.g. '01' for projection onto xy
                            or '02' for projection onto xz.
    """

    p_a = proj_axes
    dim = len(proj_axes)

    if dim == 2:
        indices = '012'
        for ix in range(len(p_a)):
            indices = indices.replace(p_a[ix], '')
        deleted_axis = int(indices)
        ax = [0, 1, 2]
        ax.remove(deleted_axis)
        result = data[:, ax]

    elif dim == 1:

        ax = int(p_a)
        result = data[:, ax]
    else:
        result = data

    return result
