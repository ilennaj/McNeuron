"""Collection of functions to train the hierarchical model."""

from __future__ import print_function

import numpy as np

import morphology_generator as models
import batch_utlis_morphology
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
        if 'dense' in l.name:
            weights = l.get_weights()
            weights = \
                [np.clip(w, weight_constraint[0],
                         weight_constraint[1]) for w in weights]
            l.set_weights(weights)
    return model


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


def plot_example_neuron(X_locations, X_parent):
    """
    Show an example neuron.

    stuff.
    """
    locations = np.squeeze(X_locations)
    prufer = np.squeeze(X_parent).argmax(axis=1)

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

    morph_model = list()

    disc_model = list()
    gan_model = list()
    level = 0
    # Discriminator
    d_model = models.discriminator(n_nodes=n_nodes[level],
                                   train_loss=train_loss)


    m_model = \
        models.generator(use_context=False,
                         n_nodes_in=n_nodes[level-1],
                         n_nodes_out=n_nodes[level],
                         batch_size=batch_size)
    stacked_model = \
        models.discriminator_on_generators(m_model,
                                           d_model,
                                           conditioning_rule=rule,
                                           input_dim=input_dim,
                                           n_nodes_in=n_nodes[level-1],
                                           n_nodes_out=n_nodes[level],
                                           use_context=False)


    disc_model.append(d_model)
    morph_model.append(m_model)
    gan_model.append(stacked_model)

    # ###############
    # Optimizers
    # ###############
    optim_d = Adagrad()  # RMSprop(lr=lr_discriminator)
    optim_g = Adagrad()  # RMSprop(lr=lr_generator)

    # ##############
    # Train
    # ##############

    # ---------------
    # Compile models
    # ---------------

    m_model = morph_model[level]
    d_model = disc_model[level]
    stacked_model = gan_model[level]


    m_model.compile(loss='mse', optimizer=optim_g)

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
                X_parent_real = \
                    batch_utlis_morphology.get_batch(training_data=training_data,
                                                     batch_size=batch_size,
                                                     batch_counter=batch_counter,
                                                     n_nodes=n_nodes[level])
                y_real = -1*np.ones((X_parent_real.shape[0], 1, 1))

                #print X_locations_real.shape, X_parent_real.shape, y_real.shape

                X_parent_gen = \
                    batch_utlis_morphology.gen_batch(batch_size=batch_size,
                                                     n_nodes=n_nodes,
                                                     level=level,
                                                     input_dim=input_dim,
                                                     morph_model=morph_model,
                                                     conditioning_rule=rule)
                y_gen = 1*np.ones((X_parent_gen.shape[0], 1, 1))

                X_parent = np.concatenate((X_parent_real,
                                           X_parent_gen), axis=0)

                y = np.concatenate((y_real, y_gen), axis=0)

                disc_loss = \
                    d_model.train_on_batch([X_parent],y)

                list_d_loss.append(disc_loss)

            if verbose:
                print("    After {0} iterations".format(d_iters))
                print("        Discriminator Loss \
                    = {0}".format(disc_loss))

            # -------------------------------------
            # Step 2: Train generator
            # -------------------------------------
            # Freeze the discriminator
            d_model.trainable = False

            noise_input = np.random.randn(batch_size, 1, input_dim)

            if level == 0:
                gen_loss = \
                    stacked_model.train_on_batch([noise_input],
                                                 y_real)
            list_g_loss.append(gen_loss)
            if verbose:
                print("")
                print("    Generator_Loss: {0}".format(gen_loss))

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

                if verbose:
                    print ("     Level #{0} Epoch #{1} Batch #{2}".
                           format(level, e, batch_counter))

                    full_adj_to_adj = \
                        batch_utlis_morphology.invert_full_matrix_np(X_parent_gen[0, :, :])

                    #neuron_object = \
                    #    plot_example_neuron_v2(X_locations_gen[0, :, :],
                    #                           full_adj_to_adj)
                    plt.show()
                    plt.figure(figsize=(10, 5))
                    plt.subplot(1, 2, 1)
                    plt.imshow(X_parent_real[0, :, :],
                               interpolation='none',
                               cmap='Greys')
                    plt.subplot(1, 2, 2)
                    plt.imshow(X_parent_gen[0, :, :],
                               interpolation='none',
                               cmap='Greys')

                    plt.figure(figsize=(10, 5))
                    plt.subplot(1, 2, 1)
                    plt.imshow(batch_utlis_morphology.invert_full_matrix_np(X_parent_real[0, :, :]),
                               interpolation='none',
                               cmap='Greys')
                    plt.subplot(1, 2, 2)
                    plt.imshow(batch_utlis_morphology.invert_full_matrix_np(X_parent_gen[0, :, :]),
                               interpolation='none',
                               cmap='Greys')
            # Display loss trace
            if 0:
                plt.figure(figsize=(3, 2))
                plt.plot(list_d_loss)
                plt.show()

            # Save models
            morph_model[level] = m_model
            disc_model[level] = d_model
            gan_model[level] = stacked_model

    return morph_model, \
        disc_model, \
        gan_model
