import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib import rc
from matplotlib.pyplot import figure
import json
import yaml
import matplotlib.ticker as ticker


def plot_(lbl: str, res_file: str, plt_type: str = 'epoch_loss', x_axis='time', plot_freq=1,
          line_width=4, marker=None, line_style=None, optima: float = 0.0, color=None, smoothen=False):
    with open(res_file, 'rb') as f:
        result = json.load(f)

    scores = []
    for run in result:
        res = run[plt_type]
        res -= optima * np.ones(len(res))
        if plt_type == 'sparse_approx_residual':
            res = np.ones(len(res)) - res
            res = np.square(res)
        res = res[::plot_freq]

        if smoothen:
            res = smooth(res, 3)
        scores += [res]

    scores = np.array(scores)

    mean = np.mean(scores, axis=0)
    std = np.std(scores, axis=0)

    UB = mean + 1 * std
    LB = mean - 1 * std

    if plt_type == 'test_acc':
        max_acc = max(mean)
        final_acc = mean[-1]
        print("{} Test Accuracy : {} +- {}".format(lbl, final_acc, min(3 * std)))
    elif plt_type == 'train_loss':
        min_loss = min(mean)
        final_loss = mean[-1]
        print("{} Train Loss : {} +- {}".format(lbl, final_loss, min(3 * std)))

    if x_axis == 'time':
        tot_cost = 0
        for res_i in result:
            print(res_i["total_cost"])
            tot_cost += res_i["total_cost"]
        tot_cost /= len(result)
        x_freq = int(tot_cost / len(mean))
        x = np.arange(len(mean)) * x_freq
    elif x_axis == 'epoch':
        x = np.arange(len(result[0][plt_type]))[::plot_freq]
    else:
        raise NotImplementedError
    plt.plot(x, mean, label=lbl, linewidth=line_width, marker=marker, linestyle=line_style, color=color)
    # plt.fill_between(x, LB, UB, alpha=0.3, linewidth=0.5, color=color)


def smooth(y, box_pts):
    box = np.ones(box_pts) / box_pts
    y_smooth = np.convolve(y, box, mode='same')
    return y_smooth


if __name__ == '__main__':
    ax = plt.figure().gca()
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    # activate latex text rendering
    rc('text', usetex=True)

    plt_cfg = yaml.load(open('plt_cfg.yaml'), Loader=yaml.FullLoader)
    # -------------------------------------------------------------------------------------------
    # ------------------------------- Modify Here -----------------------------------------------

    d = plt_cfg["dir"]
    pl_type = plt_cfg["plot_type"]
    x_ax = plt_cfg["x_ax"]
    plot_type = plt_cfg["plot_type"]
    plt_freq = plt_cfg["plot_freq"]
    smoothen = plt_cfg["smoothen"]

    for pl in plt_cfg["plots"]:
        result_file = d + pl["file"]
        lbl = pl["label"]
        lw = pl['line_width']
        ls = pl["line_style"]
        mk = pl["marker"]
        clr = pl["clr"]

        plot_(lbl=lbl,
              res_file=result_file,
              plt_type=pl_type,
              x_axis=x_ax,
              optima=0,
              line_width=lw,
              marker=mk,
              line_style=ls,
              color=clr,
              plot_freq=plt_freq,
              smoothen=smoothen)

        # Fix the X Labels
        if x_ax == 'time':
            plt.xlabel(r'$\mathcal{O}$(Time)', fontsize=10)
        elif x_ax == 'epoch':
            plt.xlabel('Epochs (Full Pass over Data)', fontsize=10)
        else:
            raise NotImplementedError

    if plot_type == 'test_error':
        plt.yscale("log")
        ax.yaxis.set_minor_formatter(ticker.ScalarFormatter())
        plt.ylabel('Test Error', fontsize=10)
    elif plot_type == 'test_acc':
        # plt.yscale("log")
        plt.ylim(60)
        plt.xlim(-5, 3000)
        ax.yaxis.set_minor_formatter(ticker.ScalarFormatter())
        plt.ylabel('Test Accuracy (%)', fontsize=10)
    elif plot_type == 'train_acc':
        plt.ylabel('Train Accuracy', fontsize=10)
    elif plot_type == 'train_loss':
        # plt.ylim(0)
        plt.yscale("log")
        ax.yaxis.set_major_formatter(ticker.ScalarFormatter())
        ax.yaxis.set_major_locator(ticker.FixedLocator([1]))
        ax.yaxis.set_minor_formatter(ticker.ScalarFormatter())
        # ax.yaxis.set_minor_locator(ticker.FixedLocator([0.5, 0.3]))
        plt.ylabel('Training Loss', fontsize=10)
    elif plot_type == 'train_error':
        plt.ylabel('Train Error', fontsize=10)
    elif plot_type == 'sparse_approx_residual':
        plt.ylabel(r'1 - $\xi$')
        plt.xlabel("Iterations", fontsize=10)
    else:
        raise NotImplementedError

    plt.legend()
    plt.grid(True, which='both', linestyle='--')
    plt.tick_params(labelsize=10)

    figure(figsize=(1, 1))
    plt.show()

# def plot_mass(masses):
#     # x_labels = ['0.1', '0.2', '0.3', '0.4', '0.5', '0.6', '0.7', '0.8', '0.9', '1']
#     # legends = ['epoch 5', 'epoch 10', 'epoch 15', 'epoch 20']
#     x_labels = ['$0\%$', '$10\%$', '$20\%$']
#     legends = [r"\textsc{SGD}",
#                r"\textsc{Gm-SGD}",
#                r"\textsc{BGmD}"]
#
#     x = np.arange(len(x_labels))
#     fig, ax = plt.subplots()
#
#     ax.set_xticks(x)
#     ax.set_yticks(np.arange(start=0, stop=100, step=10))
#     ax.set_xticklabels(x_labels)
#
#     # with open(res_file, 'rb') as f:
#     #    res = json.load(f)
#     # masses = res["frac_mass_retained"]
#     width = 0.1
#     offset = -3 / 2
#     for frac_dist, leg in zip(masses, legends):
#         # frac_dist = frac_dist[1:]
#         # frac_dist[-1] = 1
#         # plt.plot(x, frac_dist)
#         plt.bar(height=frac_dist, x=x + offset * width, width=width, label=leg)
#         offset += 1
#     ax.legend(loc='lower left', bbox_to_anchor=(0.0, 1.01), ncol=3,
#               borderaxespad=0, frameon=False, fontsize=11)
