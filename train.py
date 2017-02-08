"""Collection of functions to train the hierarchical model."""

from __future__ import print_function

import numpy as np

import models
import batch_utils
import data_transforms
import McNeuron

from keras.optimizers import RMSprop

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
    morph_model: list of keras model objects
        morphology generators for each level
    disc_model: list of keras model objects
        discriminators for each level
    gan_model: list of keras model objects
        discriminators stacked on generators for each level
    """
    # ###################################
    # Initialize models at all levels
    # ###################################
    geom_model = list()
    morph_model = list()
    disc_model = list()
    gan_model = list()

    for level in range(n_levels):
        # Discriminator
        d_model = models.discriminator(n_nodes_in=n_nodes[level])

        # Generators and GANs
        # If we are in the first level, no context
        if level == 0:
            g_model, m_model = \
                models.generator(use_context=False,
                                 n_nodes_out=n_nodes[level])
            gd_model = \
                models.discriminator_on_generators(g_model,
                                                   m_model,
                                                   d_model,
                                                   input_dim=input_dim,
                                                   use_context=False)
        # In subsequent levels, we need context
        else:
            g_model, m_model = \
                models.generator(use_context=True,
                                 n_nodes_in=n_nodes[level-1],
                                 n_nodes_out=n_nodes[level])
            gd_model = \
                models.discriminator_on_generators(g_model,
                                                   m_model,
                                                   d_model,
                                                   input_dim=input_dim,
                                                   n_nodes_in=n_nodes[level-1],
                                                   use_context=True)

        # Collect all models into a list
        disc_model.append(d_model)
        geom_model.append(g_model)
        morph_model.append(m_model)
        gan_model.append(gd_model)

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
        d_model = disc_model[level]
        gd_model = gan_model[level]

        g_model.compile(loss='mse', optimizer=optim_g)
        m_model.compile(loss='mse', optimizer=optim_g)
        d_model.trainable = False
        gd_model.compile(loss=models.wasserstein_loss, optimizer=optim_g)
        d_model.trainable = True
        d_model.compile(loss=models.wasserstein_loss, optimizer=optim_d)

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
                    X_locations_real, X_prufer_real = \
                        batch_utils.get_batch(training_data=training_data,
                                              batch_size=batch_size,
                                              batch_counter=batch_counter,
                                              n_nodes=n_nodes[level])
                    y_real = -np.ones((X_locations_real.shape[0], 1, 1))

                    #print X_locations_real.shape, X_prufer_real.shape, y_real.shape

                    X_locations_gen, X_prufer_gen = \
                        batch_utils.gen_batch(batch_size=batch_size,
                                              n_nodes=n_nodes,
                                              level=level,
                                              input_dim=input_dim,
                                              geom_model=geom_model,
                                              morph_model=morph_model)
                    y_gen = np.ones((X_locations_gen.shape[0], 1, 1))

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

                # ------------------------
                # Step 2: Train generator
                # ------------------------
                # Freeze the discriminator
                d_model.trainable = False

                if level > 0:
                    X_locations_prior_gen, X_prufer_prior_gen = \
                        batch_utils.gen_batch(batch_size=batch_size,
                                              n_nodes=n_nodes,
                                              level=level-1,
                                              input_dim=input_dim,
                                              geom_model=geom_model,
                                              morph_model=morph_model)

                noise_input = np.random.randn(batch_size, 1, input_dim)

                if level == 0:
                    gen_loss = \
                        gd_model.train_on_batch([noise_input],
                                                y_real)
                else:
                    gen_loss = \
                        gd_model.train_on_batch([X_locations_prior_gen,
                                                 X_prufer_prior_gen,
                                                 noise_input],
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
                    #save_model_weights(g_model,
                    #                   m_model,
                    #                   level,
                    #                   epoch,
                    #                   batch_counter)
                    if verbose:
                        print ("     Level #{0} Epoch #{1} Batch #{2}".
                               format(level, e, batch_counter))

                        neuron_object = \
                            plot_example_neuron(X_locations_gen[0, :, :],
                                                X_prufer_gen[0, :, :])
                        plt.show()
                # Display loss trace
                if 0:
                    plt.figure(figsize=(3, 2))
                    plt.plot(list_d_loss)
                    plt.show()

                # Save models
                geom_model[level] = g_model
                morph_model[level] = m_model
                disc_model[level] = d_model
                gan_model[level] = gd_model

    return geom_model, morph_model, disc_model, gan_model
