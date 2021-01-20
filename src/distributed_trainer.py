from src.model_manager import (get_model,
                               get_optimizer,
                               get_scheduler,
                               dist_grads_to_model,
                               flatten_grads,
                               get_loss,
                               evaluate_classifier)
from src.data_manager import process_data
from src.aggregation_manager import get_gar

import torch
from torch.utils.data import DataLoader
import numpy as np
import time

torch.manual_seed(1)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def train_and_test_model(model, criterion, optimizer, lrs, gar,
                         train_loader, test_loader, train_config, metrics):

    num_batches = train_config.get('num_clients', 1)
    num_epochs = train_config.get('global_epochs', 10)

    for epoch in range(num_epochs):
        model.to(device)
        model.train()
        G = None
        comm_rounds = 0

        print('\n--------------------------------------------------------\n'
              ' ----------------------   Epoch: {} ----------------------\n '
              '----------------------------------------------------------'.format(epoch))
        print('learning rate: {} \n'.format(optimizer.param_groups[0]['lr']))
        # ------- Training Phase --------- #
        for batch_ix, (images, labels) in enumerate(train_loader):
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

            # -------  Aggregation Step ------- #
            ix = batch_ix % num_batches
            agg_ix = (batch_ix + 1) % num_batches
            G[ix, :] = g_i

            # -------  Communication Round ------- #
            if agg_ix == 0 and batch_ix is not 0:
                agg_g = gar.aggregate(G=G)
                optimizer.zero_grad()
                # Update Model Grads with aggregated g :\tilde(g)
                dist_grads_to_model(grads=agg_g, learner=model)
                model.to(device)
                # Now Do an optimizer step with x_t+1 = x_t - \eta \tilde(g)
                optimizer.step()

                if comm_rounds % 5 == 0:
                    test_error, test_acc, _ = evaluate_classifier(model=model, data_loader=test_loader, device=device)
                    train_error, train_acc, train_loss = evaluate_classifier(model=model, data_loader=train_loader,
                                                                             criterion=criterion, device=device)

                    print('\n ---------------- Communication Round {} ------------------------'.format(comm_rounds))

                    print('--- Performance on Train Data -----')
                    print('train loss = {}\n train acc = {}'.format(train_loss, train_acc))
                    metrics["train_error"].append(train_error)
                    metrics["train_loss"].append(train_loss)
                    metrics["train_acc"].append(train_acc)

                    print('---- Generalization Performance ---- '.format(test_acc))
                    print('test acc = {}'.format(test_acc))

                    metrics["test_error"].append(test_error)
                    metrics["test_acc"].append(test_acc)

                comm_rounds += 1

        if lrs is not None:
            lrs.step()


def run_batch_train(config, metrics):
    # ------------------------ Fetch configs ----------------------- #
    pipeline = config.get('pipeline', 'default')
    data_config = config["data_config"]
    training_config = config["training_config"]

    learner_config = training_config["learner_config"]
    optimizer_config = training_config.get("optimizer_config", {})
    lrs_config = training_config.get('lrs_config')

    aggregation_config = training_config["aggregation_config"]
    compression_config = training_config["compression_config"]

    # ------------------------- Initializations --------------------- #
    model = get_model(learner_config=learner_config, data_config=data_config)
    optimizer = get_optimizer(params=model.parameters(), optimizer_config=optimizer_config)
    lrs = get_scheduler(optimizer=optimizer, lrs_config=lrs_config)
    criterion = get_loss(loss=optimizer_config.get('loss', 'ce'))
    gar = get_gar(aggregation_config=aggregation_config)

    # ------------------------- get data --------------------- #
    batch_size = data_config.get('batch_size', 1)
    data_manager = process_data(data_config=data_config)
    train_dataset, test_dataset = data_manager.download_data()

    train_loader = DataLoader(dataset=train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(dataset=test_dataset, batch_size=len(test_dataset))

    t0 = time.time()
    train_and_test_model(model=model, criterion=criterion, optimizer=optimizer, lrs=lrs,
                         gar=gar, train_loader=train_loader, test_loader=test_loader, metrics=metrics,
                         train_config=training_config)
    print("---------- End of Training -----------")
    time_taken = time.time() - t0
    metrics["runtime"] = time_taken
    print('Total Time to train = {} sec'.format(time_taken))
    return metrics