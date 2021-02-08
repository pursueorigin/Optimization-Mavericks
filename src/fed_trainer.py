# Copyright (c) Anish Acharya.
# Licensed under the MIT License

from src.model_manager import (get_model,
                               get_optimizer,
                               get_scheduler,
                               take_lrs_step,
                               get_loss,
                               evaluate_classifier)
from src.data_manager import process_data
from src.aggregation_manager import get_gar
from src.agents import FedServer, FedClient
from src.compression_manager import get_compression_operator

import torch
from typing import List, Dict
import copy
import random
import math
from torch.utils.data import DataLoader

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def init_and_train_clients(server: FedServer,
                           clients: List[FedClient],
                           pipeline: str = 'default',
                           num_local_steps: int = 1):
    w_current = server.w_current
    w_old = server.w_old

    # epoch_loss = 0
    for client in clients:
        # initialize with global params
        client.initialize_params(w_current=w_current, w_old=w_old)
        # train step
        if pipeline == 'default':
            # epoch_loss += client.train_step(num_steps=num_local_steps, device=device)
            client.train_step(num_steps=num_local_steps, device=device)
        elif pipeline == 'glomo':
            # epoch_loss += client.train_step_glomo(num_steps=num_local_steps, device=device)
            client.train_step_glomo(num_steps=num_local_steps, device=device)
        elif pipeline == 'mime':
            client.train_step_mime(client_drift=server.client_drift, server_momentum=server.mime_momentum,
                                   num_steps=num_local_steps, device=device)

        else:
            raise NotImplementedError

    # epoch_loss /= len(clients)
    # metrics["epoch_loss"].append(epoch_loss)
    # print("Epoch Loss : {}".format(epoch_loss))

    # At this point we have all the g_i computed
    # Apply Attack (Here since we can also apply co-ordinated attack)
    # TODO: Incorporate attacks


def train_and_test_model(server: FedServer,
                         clients: List[FedClient],
                         training_config: Dict,
                         data_config: Dict,
                         metrics,
                         pipeline: str = 'default'):
    print('# ------------------------------------------------- #')
    print('#          Getting and Distributing Data            #')
    print('# ------------------------------------------------- #')
    # Get Data
    data_manager = process_data(data_config=data_config)
    train_dataset, test_dataset = data_manager.download_data()

    # Distribute Data among clients
    data_manager.distribute_data(train_dataset=train_dataset, clients=clients)

    train_loader = DataLoader(dataset=train_dataset, batch_size=len(train_dataset))
    test_loader = DataLoader(dataset=test_dataset, batch_size=len(test_dataset))

    print('# ------------------------------------------------- #')
    print('#            Launching Federated Training           #')
    print('# ------------------------------------------------- #')
    device_participation = training_config.get('client_fraction', 1.0)  # partial device participation
    global_epochs = training_config.get('global_epochs', 10)
    local_epochs = training_config.get('local_epochs', 1)

    for comm_round in range(1, global_epochs + 1):
        print(' ------------------------------------------ ')
        print('         Communication Round {}             '.format(comm_round))
        print(' -------------------------------------------')
        # Sample Participating Devices
        num_devices = math.floor(len(clients) * device_participation)
        sampled_clients = random.sample(population=clients, k=num_devices)

        init_and_train_clients(server=server, clients=sampled_clients, pipeline=pipeline,
                               num_local_steps=local_epochs)

        # Now take a lrs step across all clients (** Not just sampled ones)
        current_lr = take_lrs_step(clients=clients)

        # Aggregate client grads and update server model
        if pipeline == 'default':
            server.compute_agg_grad(clients=sampled_clients)
            server.update_step()
        elif pipeline == 'glomo':
            # fix the beta parameter dynamically
            # server.beta = server.c * current_lr ** 2
            server.compute_agg_grad_glomo(clients=sampled_clients)
            server.update_step()
        elif pipeline == 'mime':
            server.compute_agg_grad_mime(clients=sampled_clients)
        else:
            raise NotImplementedError

        # Evaluate Train Loss
        # -------- Compute Metrics ---------- #
        train_error, train_acc, train_loss = evaluate_classifier(model=server.learner,
                                                                 data_loader=train_loader,
                                                                 criterion=clients[0].criterion,
                                                                 device=device)
        test_error, test_acc, _ = evaluate_classifier(model=server.learner,
                                                      data_loader=test_loader,
                                                      device=device)
        print('--- Performance on Train Data -----')
        print('train loss = {}\n train acc = {}'.format(train_loss, train_acc))
        metrics["train_error"].append(train_error)
        metrics["train_loss"].append(train_loss)
        metrics["train_acc"].append(train_acc)

        print('---- Generalization Performance ---- '.format(test_acc))
        print('test acc = {}'.format(test_acc))

        metrics["test_error"].append(test_error)
        metrics["test_acc"].append(test_acc)


def run_fed_train(config, metrics):
    pipeline = config.get('pipeline', 'default')
    data_config = config["data_config"]
    training_config = config["training_config"]

    learner_config = training_config["learner_config"]
    optimizer_config = training_config.get("optimizer_config", {})
    lrs_config = training_config.get('lrs_config', {})

    aggregation_config = training_config["aggregation_config"]
    compression_config = aggregation_config["compression_config"]

    model = get_model(learner_config=learner_config, data_config=data_config)
    gar = get_gar(aggregation_config=aggregation_config)

    print('# ------------------------------------------------- #')
    print('#               Initializing Network                #')
    print('# ------------------------------------------------- #')
    # **** Set up Server (Master Node) ****
    # --------------------------------------
    # Implementation of Dual Optimization :
    # CIte: Reddi et.al. Adaptive Federated Optimization
    server_model = copy.deepcopy(model)
    server_opt = get_optimizer(params=server_model.parameters(),
                               optimizer_config=optimizer_config.get("server_optimizer_config", {}))
    server_lrs = get_scheduler(optimizer=server_opt, lrs_config=lrs_config.get("server_optimizer_config", {}))
    server = FedServer(server_model=server_model,
                       server_optimizer=server_opt,
                       server_lrs=server_lrs,
                       gar=gar,
                       gar_config=aggregation_config)
    # *** Set up Client Nodes ****
    # -----------------------------
    clients = []
    n = training_config.get('num_clients', 10)

    for client_id in range(n):
        client = FedClient(client_id=client_id,
                           learner=copy.deepcopy(model),
                           compression=get_compression_operator(compression_config=compression_config))
        client.optimizer = get_optimizer(params=client.learner.parameters(), optimizer_config=optimizer_config)
        client.lrs = get_scheduler(optimizer=client.optimizer, lrs_config=lrs_config)
        client.criterion = get_loss(loss=optimizer_config.get('loss', 'ce'))
        client.training_config = training_config

        clients.append(client)

    train_and_test_model(server=server, clients=clients, pipeline=pipeline,
                         data_config=data_config,
                         training_config=training_config,
                         metrics=metrics)
    return metrics
