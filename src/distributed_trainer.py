# Copyright (c) Anish Acharya.
# Licensed under the MIT License

from src.model_manager import (get_model,
                               get_optimizer,
                               get_scheduler,
                               dist_grads_to_model,
                               flatten_grads,
                               get_loss,
                               evaluate_classifier)
from src.data_manager import process_data
from src.aggregation_manager import get_gar, compute_grad_stats
from src.compression_manager import SparseApproxMatrix, get_compression_operator
from src.attack_manager import get_attack

import torch
from torch.utils.data import DataLoader
import time
from tqdm import tqdm
import numpy as np

# Reproducibility Checks
torch.backends.cudnn.deterministic = True

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def train_and_test_model(model, criterion, optimizer, lrs, gar,
                         train_loader, test_loader, train_config, metrics,
                         sparse_selection=None, attack_model=None, C=None):

    num_batches = train_config.get('num_clients', 1)
    num_epochs = train_config.get('global_epochs', 10)
    compute_grad_stat_flag = train_config.get('compute_grad_stats', False)

    epoch = 0

    while epoch < num_epochs:
        model.to(device)
        model.train()
        G = None
        epoch_grad_cost = 0
        epoch_agg_cost = 0
        epoch_gm_iter = 0
        epoch_sparse_cost = 0

        # ------- Training Phase --------- #
        print('epoch {}/{} || learning rate: {}'.format(epoch, num_epochs, optimizer.param_groups[0]['lr']))
        p_bar = tqdm(total=len(train_loader))
        p_bar.set_description("Epoch Progress: ")

        for batch_ix, (images, labels) in enumerate(train_loader):
            t_iter = time.time()

            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            optimizer.zero_grad()
            loss = criterion(outputs, labels)
            loss.backward()
            # Note: No Optimizer Step yet.

            g_i = flatten_grads(learner=model)
            if G is None:
                d = len(g_i)
                G = np.zeros((num_batches, d), dtype=g_i.dtype)

            ix = batch_ix % num_batches
            agg_ix = (batch_ix + 1) % num_batches
            G[ix, :] = g_i

            iteration_time = time.time() - t_iter
            epoch_grad_cost += iteration_time
            metrics["num_iteration"] += 1
            p_bar.update()

            if agg_ix == 0 and batch_ix is not 0:
                # -------  Server / Aggregation Step ------- #
                lr = optimizer.param_groups[0]['lr']

                # Adversarial Attack
                if attack_model is not None:
                    G = attack_model.launch_attack(G=G)

                # Compress each vector before aggregation
                if C is not None:
                    for ix, g_i in enumerate(G):
                        G[ix, :] = C.compress(g_i, lr=lr)

                # --- Gradient Aggregation Step -------- ###
                # Sparse Approximation of G
                I_k = None
                if sparse_selection is not None:
                    t0 = time.time()
                    G, I_k = sparse_selection.sparse_approx(G=G, lr=lr)
                    epoch_sparse_cost += time.time() - t0

                # Gradient aggregation
                agg_g = gar.aggregate(G=G, ix=I_k)
                metrics["num_agg_steps"] += 1
                epoch_gm_iter += gar.num_iter
                epoch_agg_cost += gar.agg_time
                # Reset Agg time
                gar.agg_time = 0

                # Update Model Grads with aggregated g : i.e. compute \tilde(g)
                optimizer.zero_grad()
                dist_grads_to_model(grads=agg_g, learner=model)
                model.to(device)
                # Now Do an optimizer step with x_t+1 = x_t - \eta \tilde(g)
                optimizer.step()

        p_bar.close()
        if lrs is not None:
            lrs.step()

        # Compute gradient statistics
        # if compute_grad_stat_flag is True:
        #     print("Computing Additional Stats on G")
        #     compute_grad_stats(G=G, metrics=metrics)

        train_loss = evaluate_classifier(model=model, train_loader=train_loader, test_loader=test_loader,
                                         metrics=metrics, criterion=criterion, device=device,
                                         epoch=epoch, num_epochs=num_epochs)
        # Stop if diverging
        if (train_loss > 1e3) | np.isnan(train_loss) | np.isinf(train_loss):
            epoch = num_epochs
            print(" *** Training is Diverging - Stopping !!! *** ")

        epoch += 1
        # update Epoch Complexity metrics
        print("Epoch Grad Cost: {}".format(epoch_grad_cost))
        metrics["epoch_grad_cost"].append(epoch_grad_cost)
        print("Epoch Aggregation Cost: {}".format(epoch_agg_cost))
        metrics["epoch_agg_cost"].append(epoch_agg_cost)
        print("Epoch GM iterations: {}".format(epoch_gm_iter))
        metrics["epoch_gm_iter"].append(epoch_gm_iter)
        print("Epoch Sparse Approx Cost: {}".format(epoch_sparse_cost))
        metrics["epoch_sparse_approx_cost"].append(epoch_sparse_cost)

    # Update Total Complexities
    metrics["total_cost"] = sum(metrics["epoch_grad_cost"]) + sum(metrics["epoch_agg_cost"])
    metrics["avg_gm_cost"] = sum(metrics["epoch_agg_cost"]) / sum(metrics["epoch_gm_iter"])


def run_batch_train(config, metrics):
    # ------------------------ Fetch configs ----------------------- #
    print('---- Fetching configs -----')
    seed = config["seed"]

    np.random.seed(seed)
    torch.manual_seed(seed)

    data_config = config["data_config"]
    training_config = config["training_config"]

    learner_config = training_config["learner_config"]
    optimizer_config = training_config.get("optimizer_config", {})

    client_optimizer_config = optimizer_config.get("client_optimizer_config", {})
    client_lrs_config = optimizer_config.get('client_lrs_config')

    aggregation_config = training_config["aggregation_config"]
    sparse_approx_config = aggregation_config.get("sparse_approximation_config", {})
    compression_config = aggregation_config.get("compression_config", {})
    attack_config = aggregation_config.get("attack_config", {})

    # ------------------------- get data --------------------- #
    batch_size = data_config.get('batch_size', 1)
    data_manager = process_data(data_config=data_config)
    train_dataset, test_dataset = data_manager.download_data()

    train_loader = DataLoader(dataset=train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(dataset=test_dataset, batch_size=batch_size)

    # ------------------------- Initializations --------------------- #
    client_model = get_model(learner_config=learner_config, data_config=data_config, seed=seed)
    client_optimizer = get_optimizer(params=client_model.parameters(), optimizer_config=client_optimizer_config)
    client_lrs = get_scheduler(optimizer=client_optimizer, lrs_config=client_lrs_config)
    criterion = get_loss(loss=client_optimizer_config.get('loss', 'ce'))

    # gradient aggregation related objects
    # gar
    gar = get_gar(aggregation_config=aggregation_config)
    # sparse approximation of the gradients before aggregating
    sparse_rule = sparse_approx_config.get('rule', None)
    sparse_selection = SparseApproxMatrix(conf=sparse_approx_config) if sparse_rule in ['active_norm', 'random'] \
        else None
    # for adversarial - get attack model
    attack_model = get_attack(attack_config=attack_config)
    # gradient compression object
    C = get_compression_operator(compression_config=compression_config)

    # ------------------------- Run Training --------------------- #
    train_and_test_model(model=client_model, criterion=criterion, optimizer=client_optimizer, lrs=client_lrs,
                         gar=gar, sparse_selection=sparse_selection, attack_model=attack_model, C=C,
                         train_loader=train_loader, test_loader=test_loader,
                         metrics=metrics, train_config=training_config)

    return metrics
