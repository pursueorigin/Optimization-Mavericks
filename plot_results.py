import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import matplotlib.ticker as ticker
from matplotlib.ticker import ScalarFormatter
from matplotlib import rc
from matplotlib.pyplot import figure
import json
from typing import List, Dict
from src.aggregation_manager import get_gar
import time
from numpyencoder import NumpyEncoder
from src.compression_manager import SparseApproxMatrix


def plot_driver(label: str, res_file: str, plt_type: str = 'epoch_loss',
                line_width=2, marker=None, line_style=None, optima: float = 0.0,
                sampling_freq: int = 1):
    with open(res_file, 'rb') as f:
        result = json.load(f)

    res = result[plt_type]
    # res = res[0::sampling_freq]
    res -= optima * np.ones(len(res))

    x = np.arange(len(res)) + np.ones(len(res))
    x *= sampling_freq  # * sampling_freq
    plt.plot(x, res, label=label, linewidth=line_width, marker=marker, linestyle=line_style)


def plot_time(label: str, res_file: str, plt_type: str = 'epoch_loss',
              line_width=2, marker=None, line_style=None, optima: float = 0.0,
              sampling_freq: int = 1):
    with open(res_file, 'rb') as f:
        result = json.load(f)

    res = result[plt_type]  # [:35]
    # res = res[0::sampling_freq]
    res -= optima * np.ones(len(res))

    x_freq = int(result["total_cost"] / len(res))
    x = np.arange(len(res)) * x_freq
    # x = np.arange(len(res)) + np.ones(len(res))
    # x *= sampling_freq # * sampling_freq
    plt.plot(x, res, label=label, linewidth=line_width, marker=marker, linestyle=line_style)


def smooth(y, box_pts):
    box = np.ones(box_pts) / box_pts
    y_smooth = np.convolve(y, box, mode='same')
    return y_smooth


def plot_timing(res_file: str, label):
    # d = [100, 1000, 10000, 100000]
    with open(res_file, 'rb') as f:
        res = json.load(f)
    d = list(res.keys())
    t = list(res.values())

    # plt.yscale('log')
    t = smooth(y=t, box_pts=1)

    plt.scatter(d, t, label=label, marker='.')
    plt.plot(d, t, linestyle='dashed')


# def plot_mass(res_file):
def plot_mass(masses):
    # x_labels = ['0.1', '0.2', '0.3', '0.4', '0.5', '0.6', '0.7', '0.8', '0.9', '1']
    # legends = ['epoch 5', 'epoch 10', 'epoch 15', 'epoch 20']

    x_labels = ['$0\%$', '$10\%$', '$20\%$']
    legends = [r"\textsc{SGD}",
               r"\textsc{Gm-SGD}",
               r"\textsc{BGmD}"]

    x = np.arange(len(x_labels))

    fig, ax = plt.subplots()

    ax.set_xticks(x)
    ax.set_yticks(np.arange(start=0, stop=100, step=10))
    ax.set_xticklabels(x_labels)

    # with open(res_file, 'rb') as f:
    #    res = json.load(f)
    # masses = res["frac_mass_retained"]
    width = 0.1
    offset = -3 / 2
    for frac_dist, leg in zip(masses, legends):
        # frac_dist = frac_dist[1:]
        # frac_dist[-1] = 1
        # plt.plot(x, frac_dist)
        plt.bar(height=frac_dist, x=x + offset * width, width=width, label=leg)
        offset += 1
    ax.legend(loc='lower left', bbox_to_anchor=(0.0, 1.01), ncol=3,
              borderaxespad=0, frameon=False, fontsize=11)


def plot_metrics():
    ax = plt.figure().gca()
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    # activate latex text rendering
    rc('text', usetex=True)

    # -------------------------------------------------------------------------------------------
    # ------------------------------- Modify Here -----------------------------------------------
    d = 'result_dumps/fmnist/'

    o = [
        'mean.ag.49',
        'gm.ag.49',
        'cm.ag.49',
        #'bgm'
    ]
    labels = [
        r"\textsc{SGD}",
        r"\textsc{Gm-SGD}",
        r"\textsc{Cm-SGD}",
        # r"\textsc{BGm-SGD}",
    ]
    plot_type = 'train_loss'
    x_ax = 'epoch'
    sampling_freq = 1

    plt.ylim(top=1, bottom=0.1)

    for op, label in zip(o, labels):
        result_file = d + op

        if x_ax is 'time':
            plot_time(label=label, res_file=result_file,
                      plt_type=plot_type, optima=0, line_width=4,
                      sampling_freq=sampling_freq)
            plt.xlabel('Time (seconds)', fontsize=10)
        else:
            plot_driver(label=label, res_file=result_file,
                        plt_type=plot_type, optima=0, line_width=4,
                        sampling_freq=sampling_freq)
            plt.xlabel('Epochs (Full Pass over Data)', fontsize=10)

    if plot_type is 'test_error':
        plt.ylabel('Test Error', fontsize=10)
    elif plot_type is 'test_acc':
        plt.ylabel('Test Accuracy', fontsize=10)
    elif plot_type is 'train_acc':
        plt.ylabel('Train Accuracy', fontsize=10)
    elif plot_type is 'train_loss':
        plt.ylabel('Training Loss', fontsize=10)
    elif plot_type is 'train_error':
        plt.ylabel('Train Error', fontsize=10)
    else:
        raise NotImplementedError

    plt.legend()
    plt.grid(True, which='both', linestyle='--')
    plt.tick_params(labelsize=10)

    figure(figsize=(1, 1))
    plt.show()


def get_runtime(gar, X, repeat: int = 1):
    T = 0
    for it in range(repeat):
        t0 = time.time()
        _ = gar.aggregate(G=X)
        T += time.time() - t0
    T /= repeat
    return T


def compare_gar_speed(agg_config: Dict,
                      sparse_approximation_config=None):
    # d = [100, 1000, 10000, 100000]
    d = [int(1e3), int(5e3), int(1e4), int(5e4)]
    n = 500
    res = {}
    gar = get_gar(aggregation_config=agg_config)

    for dim in d:
        sparse_approx_op = SparseApproxMatrix(conf=sparse_approximation_config)
        # generate n points in d dimensions

        X = np.random.normal(0, 0.3, (n, dim))
        k = sparse_approximation_config['frac_coordinates']
        ix = list(range(int(k * dim)))
        X_sparse = X[:, ix]

        if sparse_approximation_config["rule"] is not None:
            # Compute time for sparse approx.
            # t0 = time.time()
            # _ = sparse_approx_op.sparse_approx(G=X)
            # t = time.time() - t0
            # Compute GM time
            t = get_runtime(gar=gar, X=X_sparse)
        else:
            t = get_runtime(gar=gar, X=X)
        res[dim] = t

    return res


def runtime_exp():
    op_file = 'result_dumps/timing_exp/trimmed_mean'
    aggregation_config = \
        {
            "gar": "trimmed_mean",
            "krum_config": {"krum_frac": 0.3},
        }

    sparse_approximation_config = {
        "rule": 'active_norm',
        "axis": 'column',
        "frac_coordinates": 1,
    }

    results = compare_gar_speed(agg_config=aggregation_config,
                                sparse_approximation_config=sparse_approximation_config)

    with open(op_file, 'w+') as f:
        json.dump(results, f, indent=4, ensure_ascii=False, cls=NumpyEncoder)


if __name__ == '__main__':
    plot_metrics()
    # runtime_exp()
