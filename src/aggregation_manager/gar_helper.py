# Copyright (c) Anish Acharya.
# Licensed under the MIT License

from .mean import Mean
from .median import GeometricMedian, CoordinateWiseMedian
from .trimmed_mean import TrimmedMean
from .krum import Krum
from .norm_clipping import NormClipping
from typing import Dict
import numpy as np


def get_gar(aggregation_config: Dict):
    gar = aggregation_config.get("gar", 'mean')
    print('--------------------------------')
    print('Initializing {} GAR'.format(gar))
    print('--------------------------------')
    if gar == 'mean':
        return Mean(aggregation_config=aggregation_config)
    elif gar == 'geo_med':
        return GeometricMedian(aggregation_config=aggregation_config)
    elif gar == 'co_med':
        return CoordinateWiseMedian(aggregation_config=aggregation_config)
    elif gar == 'norm_clip':
        return NormClipping(aggregation_config=aggregation_config)
    elif gar == 'krum':
        return Krum(aggregation_config=aggregation_config)
    elif gar == 'trimmed_mean':
        return TrimmedMean(aggregation_config=aggregation_config)
    else:
        raise NotImplementedError


def compute_grad_stats(G: np.ndarray, metrics: Dict):
    norm_dist = np.linalg.norm(G, axis=0)
    # metrics["grad_norm_dist"].append(norm_dist)

    # compute cdf / mass retained
    sorted_dist = np.sort(norm_dist)[::-1]
    # sorted_dist /= sum(sorted_dist)

    frac_mass_retained = np.cumsum(sorted_dist)
    frac_mass_retained /= frac_mass_retained[-1]

    ix = np.linspace(0, len(norm_dist)-1, 11)
    ix = np.floor(ix)
    ix = ix.astype(int)
    metrics["frac_mass_retained"].append(frac_mass_retained[ix])
