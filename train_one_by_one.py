"""Collection of functions to train the hierarchical model."""

from __future__ import print_function

import numpy as np

import models_generate_parents as models
import batch_utils
import data_transforms
import McNeuron

from keras.optimizers import RMSprop, Adagrad, Adam

import matplotlib.pyplot as plt


def clip_weights(model, weight_constraint):
    """
    Clip weights of a keras model to be bounded by given constraints.

    Parameters
    ----------
    model: keras model object
        model for which weights need to be clipped
    weight_constraint:

    Returns
    -------
    model: keras model object
        model with clipped weights
    """
    for l in model.layers:
        if True:  # 'dense' in l.name:
            weights = l.get_weights()
            weights = \
                [np.clip(w, weight_constraint[0],
                         weight_constraint[1]) for w in weights]
            l.set_weights(weights)
    return model


def save_model_weights():
    """
    cool stuff.
    """


def plot_example_neuron_v2(X_locations, X_parent):
    """
    Show an example neuron.

    stuff.
    """
    locations = np.squeeze(X_locations)
    parent = np.squeeze(X_parent).argmax(axis=1) + 1

    M = np.zeros([parent.shape[0] + 1, 7])
    M[:, 0] = np.arange(1, parent.shape[0] + 2)
    M[0, 1] = 1
    M[1:, 1] = 2
    M[1:, 2:5] = locations
    M[1:, 6] = parent
    M[0, 6] = -1
    neuron_object = McNeuron.Neuron(file_format='Matrix of swc', input_file=M)

    McNeuron.visualize.plot_2D(neuron_object)
    return neuron_object


def plot_example_neuron(X_locations, X_prufer):
    """
    Show an example neuron.

    stuff.
    """
    locations = np.squeeze(X_locations)
    prufer = np.squeeze(X_prufer).argmax(axis=1)

    soma = np.array([[0., 0., 0.]])
    np.append(soma, np.squeeze(locations), axis=0)

    parents = np.array(data_transforms.decode_prufer(list(prufer)))
    parents_reordered, locations_reordered = \
        data_transforms.reordering_prufer(parents, np.squeeze(locations))

    prufer_reordered = data_transforms.encode_prufer(list(parents_reordered))

    input_code = dict()
    input_code['morphology'] = np.array(prufer_reordered)
    input_code['geometry'] = np.squeeze(locations_reordered)
    neuron_object = \
        data_transforms.make_swc_from_prufer_and_locations(input_code)

    McNeuron.visualize.plot_2D(neuron_object)
    return neuron_object


def train_model(training_data=None,
                n_levels=3,
                n_nodes=[10, 20, 40],
                input_dim=100,
                n_epochs=25,
                batch_size=64,
                n_batch_per_epoch=100,
                d_iters=20,
                lr_discriminator=0.005,
                lr_generator=0.00005,
                weight_constraint=[-0.01, 0.01],
                rule='mgd',
                train_one_by_one=False,
                train_loss='wasserstein_loss',
                verbose=True):
    """
    Train the hierarchical model.

    Progressively generate trees with
    more and more nodes.

    Parameters
    ----------
    training_data: dict of dicts
        each inner dict is an array
        'geometry': 3-d arrays (locations)
            n_samples x n_nodes - 1 x 3
        'morphology': 2-d arrays
            n_samples x n_nodes - 2 (prufer sequences)
        example: training_data['geometry']['n20'][0:10, :, :]
                 gives the geometry for the first 10 neurons
                 training_data['geometry']['n20'][0:10, :]
                 gives the prufer sequences for the first 10 neurons
                 here, 'n20' indexes a key corresponding to
                 20-node downsampled neurons.
    n_levels: int
        number of levels in the hierarchy
    n_nodes: list of length n_levels
        specifies the number of nodes for each level.
        should be consistent with training data.
    input_dim: int
        dimensionality of noise input
    n_epochs:
        number of epochs over training data
    batch_size:
        batch size
    n_batch_per_epoch: int
        number of batches per epoch
    d_iters: int
        number of iterations to train discriminator
    lr_discriminator: float
        learning rate for optimization of discriminator
    lr_generator: float
        learning rate for optimization of generator
    weight_constraint: array
        upper and lower bounds of weights (to clip)
    verbose: bool
        print relevant progress throughout training

    Returns
    -------
    geom_model: list of keras model objects
        geometry generators for each level
    cond_geom_model: list of keras model objects
        conditional geometry generators for each level
    morph_model: list of keras model objects
        morphology generators for each level
    cond_morph_model: list of keras model objects
        conditional morphology generators for each level
    disc_model: list of keras model objects
        discriminators for each level
    gan_model: list of keras model objects
        discriminators stacked on generators for each level
    """
    # ###################################
    # Initialize models at all levels
    # ###################################
    geom_model = list()
    cond_geom_model = list()
    morph_model = list()
    cond_morph_model = list()
    disc_model = list()
    gan_model = list()

    for level in range(n_levels):
        # Discriminator
        d_model = models.discriminator(n_nodes_in=n_nodes[level],
                                       train_loss=train_loss)

        # Generators and GANs
        # If we are in the first level, no context
        if level == 0:
            g_model, cg_model, m_model, cm_model = \
                models.generator(use_context=False,
                                 n_nodes_in=n_nodes[level-1],
                                 n_nodes_out=n_nodes[level],
                                 batch_size=batch_size)
            stacked_model = \
                models.discriminator_on_generators(g_model,
                                                   cg_model,
                                                   m_model,
                                                   cm_model,
                                                   d_model,
                                                   conditioning_rule=rule,
                                                   input_dim=input_dim,
                                                   n_nodes_in=n_nodes[level-1],
                                                   n_nodes_out=n_nodes[level],
                                                   use_context=False)
        # In subsequent levels, we need context
        else:
            g_model, cg_model, m_model, cm_model = \
                models.generator(use_context=True,
                                 n_nodes_in=n_nodes[level-1],
                                 n_nodes_out=n_nodes[level])
            stacked_model = \
                models.discriminator_on_generators(g_model,
                                                   cg_model,
                                                   m_model,
                                                   cm_model,
                                                   d_model,
                                                   conditioning_rule=rule,
                                                   input_dim=input_dim,
                                                   n_nodes_in=n_nodes[level-1],
                                                   n_nodes_out=n_nodes[level],
                                                   use_context=True)

        # Collect all models into a list
        disc_model.append(d_model)
        geom_model.append(g_model)
        cond_geom_model.append(cg_model)
        morph_model.append(m_model)
        cond_morph_model.append(cm_model)
        gan_model.append(stacked_model)

    # ###############
    # Optimizers
    # ###############
    optim_d = RMSprop(lr=lr_discriminator)
    optim_g = RMSprop(lr=lr_generator)

    # ##############
    # Train
    # ##############
    for level in range(n_levels):
        # ---------------
        # Compile models
        # ---------------
        g_model = geom_model[level]
        m_model = morph_model[level]
        cg_model = cond_geom_model[level]
        cm_model = cond_morph_model[level]
        d_model = disc_model[level]
        stacked_model = gan_model[level]

        g_model.compile(loss='mse', optimizer=optim_g)
        m_model.compile(loss='mse', optimizer=optim_g)
        cg_model.compile(loss='mse', optimizer=optim_g)
        cm_model.compile(loss='mse', optimizer=optim_g)

        d_model.trainable = False

        if train_loss == 'wasserstein_loss':
            stacked_model.compile(loss=models.wasserstein_loss,
                                  optimizer=optim_g)
        else:
            stacked_model.compile(loss='binary_crossentropy',
                                  optimizer=optim_g)

        d_model.trainable = True

        if train_loss == 'wasserstein_loss':
            d_model.compile(loss=models.wasserstein_loss,
                            optimizer=optim_d)
        else:
            d_model.compile(loss='binary_crossentropy',
                            optimizer=optim_d)

        if verbose:
            print("")
            print(20*"=")
            print("Level #{0}".format(level))
            print(20*"=")
        # -----------------
        # Loop over epochs
        # -----------------
        for e in range(n_epochs):
            batch_counter = 1
            g_iters = 0

            if verbose:
                print("")
                print("    Epoch #{0}".format(e))
                print("")

            while batch_counter < n_batch_per_epoch:
                list_d_loss = list()
                list_g_loss = list()
                # ----------------------------
                # Step 1: Train discriminator
                # ----------------------------
                for d_iter in range(d_iters):

                    # Clip discriminator weights
                    d_model = clip_weights(d_model, weight_constraint)

                    # Create a batch to feed the discriminator model
                    select = range((batch_counter - 1) * batch_size,
                                   batch_counter * batch_size)
                    X_locations_real = \
                        training_data['geometry']['n'+str(n_nodes[level])][select, :, :]

                    X_prufer_cut = \
                        np.reshape(training_data['morphology']['n'+str(n_nodes[level])][select, :],
                                   [1, (n_nodes[level] - 1) * batch_size])

                    X_prufer_real = \
                        batch_utils.get_batch(X_prufer_cut=X_prufer_cut,
                                              batch_size=batch_size,
                                              n_nodes=n_nodes[level])

                    # if train_loss == 'wasserstein_loss':
                    y_real = -np.ones((X_locations_real.shape[0], 1, 1))
                    # else:
                        # y_real = np.ones((X_locations_real.shape[0], 1, 1))

                    #print X_locations_real.shape, X_prufer_real.shape, y_real.shape

                    X_locations_gen, X_prufer_gen = \
                        batch_utils.gen_batch(batch_size=batch_size,
                                              n_nodes=n_nodes,
                                              level=level,
                                              input_dim=input_dim,
                                              geom_model=geom_model,
                                              cond_geom_model=cond_geom_model,
                                              morph_model=morph_model,
                                              cond_morph_model=cond_morph_model,
                                              conditioning_rule=rule)
                    # if train_loss == 'wasserstein_loss':
                    y_gen = np.ones((X_locations_gen.shape[0], 1, 1))
                    # else:
                    #     y_gen = np.zeros((X_locations_gen.shape[0], 1, 1))

                    #print X_locations_gen.shape, X_prufer_gen.shape, y_gen.shape

                    X_locations = np.concatenate((X_locations_real,
                                                 X_locations_gen), axis=0)

                    X_prufer = np.concatenate((X_prufer_real,
                                               X_prufer_gen), axis=0)

                    y = np.concatenate((y_real, y_gen), axis=0)

                    # Update the discriminator
                    #d_model.summary()
                    disc_loss = \
                        d_model.train_on_batch([X_locations,
                                                X_prufer],
                                               y)

                    list_d_loss.append(disc_loss)

                if verbose:
                    print("    After {0} iterations".format(d_iters))
                    print("        Discriminator Loss \
                        = {0}".format(disc_loss))

                # -------------------------------------
                # Step 2: Train generators alternately
                # -------------------------------------
                # Freeze the discriminator
                d_model.trainable = False

                if train_one_by_one is True:
                    # For odd iterations
                    if batch_counter % 20 in range(10):
                        # Freeze the conditioned generator
                        if rule == 'mgd':
                            cg_model.trainable = False
                        elif rule == 'gmd':
                            cm_model.trainable = False
                    # For even iterations
                    else:
                        # Freeze the unconditioned generator
                        if rule == 'mgd':
                            g_model.trainable = False
                        elif rule == 'gmd':
                            m_model.trainable = False

                if level > 0:
                    X_locations_prior_gen, X_prufer_prior_gen = \
                        batch_utils.gen_batch(batch_size=batch_size,
                                              n_nodes=n_nodes,
                                              level=level-1,
                                              input_dim=input_dim,
                                              geom_model=geom_model,
                                              cond_geom_model=cond_geom_model,
                                              morph_model=morph_model,
                                              cond_morph_model=cond_morph_model,
                                              conditioning_rule=rule)

                noise_input = np.random.randn(batch_size, 1, input_dim)

                if level == 0:
                    gen_loss = \
                        stacked_model.train_on_batch([noise_input],
                                                     y_real)
                else:
                    gen_loss = \
                        stacked_model.train_on_batch([X_locations_prior_gen,
                                                      X_prufer_prior_gen,
                                                      noise_input],
                                                     y_real)

                list_g_loss.append(gen_loss)
                if verbose:
                    print("")
                    print("    Generator_Loss: {0}".format(gen_loss))

                if train_one_by_one is True:
                    # For odd iterations
                    if batch_counter % 20 in range(10):
                        # Unfreeze the conditioned generator
                        if rule == 'mgd':
                            cg_model.trainable = True
                        elif rule == 'gmd':
                            cm_model.trainable = True
                    # For even iterations
                    else:
                        # Unfreeze the unconditioned generator
                        if rule == 'mgd':
                            g_model.trainable = True
                        elif rule == 'gmd':
                            m_model.trainable = True

                # Unfreeze the discriminator
                d_model.trainable = True

                # ---------------------
                # Step 3: Housekeeping
                # ---------------------
                g_iters += 1
                batch_counter += 1

                # Save model weights (few times per epoch)
                print(batch_counter)
                if batch_counter % 25 == 0:
                    #save_model_weights(g_model,
                    #                   m_model,
                    #                   level,
                    #                   epoch,
                    #                   batch_counter)
                    if verbose:
                        print ("     Level #{0} Epoch #{1} Batch #{2}".
                               format(level, e, batch_counter))

                        full_adj_to_adj = \
                            batch_utils.invert_full_matrix_np(X_prufer_gen[0, :, :])

                        # neuron_object = \
                        #     plot_example_neuron_v2(X_locations_gen[0, :, :],
                        #                            full_adj_to_adj)

                        neuron_object = \
                            plot_example_neuron_v2(X_locations_gen[0, :, :],
                                                   full_adj_to_adj)

                        plt.show()
                        plt.figure(figsize=(10, 5))
                        plt.subplot(1, 2, 1)
                        plt.imshow(X_prufer_real[0, :, :],
                                   interpolation='none',
                                   cmap='Greys')
                        plt.subplot(1, 2, 2)
                        plt.imshow(X_prufer_gen[0, :, :],
                                   interpolation='none',
                                   cmap='Greys')

                        plt.figure(figsize=(10, 5))
                        plt.subplot(1, 2, 1)
                        plt.imshow(batch_utils.invert_full_matrix_np(X_prufer_real[0, :, :]),
                                   interpolation='none',
                                   cmap='Greys')
                        plt.subplot(1, 2, 2)
                        plt.imshow(batch_utils.invert_full_matrix_np(X_prufer_gen[0, :, :]),
                                   interpolation='none',
                                   cmap='Greys')
                # Display loss trace
                if verbose:
                    plt.figure(figsize=(3, 2))
                    plt.plot(list_d_loss)
                    plt.show()

                # Save models
                geom_model[level] = g_model
                cond_geom_model[level] = cg_model
                morph_model[level] = m_model
                cond_morph_model[level] = cm_model
                disc_model[level] = d_model
                gan_model[level] = stacked_model

    return geom_model, \
        cond_geom_model, \
        morph_model, \
        cond_morph_model, \
        disc_model, \
        gan_model
