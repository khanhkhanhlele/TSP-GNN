#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys, os, time, shutil, random, argparse
import tensorflow as tf
import numpy as np
from itertools import islice
from functools import reduce

from model import build_network
from dataset import create_dataset
from instance_loader import InstanceLoader
from util import load_weights, save_weights

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

tf.compat.v1.disable_eager_execution()

def run_batch(sess, model, batch, batch_i, epoch_i, time_steps, train=False, verbose=True):

    EV, W, C, route_exists, n_vertices, n_edges = batch

    # Compute the number of problems
    n_problems = n_vertices.shape[0]

    # Define feed dict
    feed_dict = {
        model['EV']: EV,
        model['W']: W,
        model['C']: C,
        model['time_steps']: time_steps,
        model['route_exists']: route_exists,
        model['n_vertices']: n_vertices,
        model['n_edges']: n_edges
    }

    if train:
        outputs = [model['train_step'], model['loss'], model['acc'], model['predictions'], model['TP'], model['FP'], model['TN'], model['FN']]
    else:
        outputs = [model['loss'], model['acc'], model['predictions'], model['TP'], model['FP'], model['TN'], model['FN']]
    #end

    # Run model
    loss, acc, predictions, TP, FP, TN, FN = sess.run(outputs, feed_dict = feed_dict)[-7:]

    if verbose:
        # Print stats
        print('{train_or_test} Epoch {epoch_i} Batch {batch_i}\t|\t(n,m,batch size)=({n},{m},{batch_size})\t|\t(Loss,Acc)=({loss:.4f},{acc:.4f})\t|\tAvg. (Sat,Prediction)=({avg_sat:.4f},{avg_pred:.4f})'.format(
            train_or_test = 'Train' if train else 'Test',
            epoch_i = epoch_i,
            batch_i = batch_i,
            loss = loss,
            acc = acc,
            n = np.sum(n_vertices),
            m = np.sum(n_edges),
            batch_size = n_vertices.shape[0],
            avg_sat = np.mean(route_exists),
            avg_pred = np.mean(np.round(predictions))
            ),
            flush = True
        )
    #end

    return loss, acc, np.mean(route_exists), np.mean(predictions), TP, FP, TN, FN
#end

def summarize_epoch(epoch_i, loss, acc, sat, pred, train=False):
    print('{train_or_test} Epoch {epoch_i} Average\t|\t(Loss,Acc)=({loss:.4f},{acc:.4f})\t|\tAvg. (Sat,Pred)=({avg_sat:.4f},{avg_pred:.4f})'.format(
        train_or_test = 'Train' if train else 'Test',
        epoch_i = epoch_i,
        loss = np.mean(loss),
        acc = np.mean(acc),
        avg_sat = np.mean(sat),
        avg_pred = np.mean(pred)
        ),
        flush = True
    )
#end

def ensure_datasets(batch_size, train_params, test_params):
    """
        Subroutine to ensure that train and test datasets exist
    """
    
    if not os.path.isdir('instances/train'):
        print('Creating {} Train instances'.format(train_params['samples']), flush=True)
        create_dataset(
            'instances/train',
            train_params['n_min'], train_params['n_max'],
            conn_min=train_params['conn_min'], conn_max=train_params['conn_max'],
            samples=train_params['samples'],
            distances=train_params['distances'])
    #end

    if not os.path.isdir('instances/test'):
        print('Creating {} Test instances'.format(test_params['samples']), flush=True)
        create_dataset(
            'instances/test',
            test_params['n_min'], test_params['n_max'],
            conn_min=test_params['conn_min'], conn_max=test_params['conn_max'],
            samples=test_params['samples'],
            distances=test_params['distances'])
    #end
#end

if __name__ == '__main__':
    
    # Define argument parser
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('-d', default=64, type=int, help='Embedding size for vertices and edges')
    parser.add_argument('-timesteps', default=32, type=int, help='# Timesteps')
    parser.add_argument('-dev', default=0.02, type=float, help='Target cost deviation')
    parser.add_argument('-epochs', default=10, type=int, help='Training epochs')
    parser.add_argument('-batchsize', default=8, type=int, help='Batch size')
    parser.add_argument('-seed', type=int, default=42, help='RNG seed for Python, Numpy and Tensorflow')
    parser.add_argument('--load', const=True, default=False, action='store_const', help='Load model checkpoint?')
    parser.add_argument('-load_from', default=None, help='Load weights from this path')
    parser.add_argument('--save', const=True, default=False, action='store_const', help='Save model?')
    parser.add_argument('-distances', default='euc_2D', help='What type of distances? (euc_2D or random)')
    parser.add_argument('-cmin', default=1, type=float, help='Min. connectivity')
    parser.add_argument('-cmax', default=1, type=float, help='Max. connectivity')

    # Parse arguments from command line
    args = parser.parse_args()

    print('\n-------------------------------------------\n')

    if vars(args)['load_from'] is not None:
        loadpath = vars(args)['load_from']
        print('Load path: {}'.format(loadpath))
    elif vars(args)['load']:
        print('Found the following training setups:')
        for i,directory in enumerate(os.listdir('training')):
            print('\t{i}. {dir}'.format(i=i+1,dir=directory))
        #end
        n = len(os.listdir('training'))
        option = input('\tLoad checkpoint from which training setup? ')
        while not option.isdigit() or int(option)-1 not in range(n):
             option = input('Invalid option. Type an integer 1 <= x <= {n}: '.format(n=n))
        #end
        print('Found the following checkpoints:')
        for i,directory in enumerate(os.listdir('training/{}/checkpoints'.format(os.listdir('training')[int(option)-1]))):
            print('\t{i}. {dir}'.format(i=i+1,dir=directory))
        #end
        n2 = len(os.listdir('training/{}/checkpoints'.format(os.listdir('training')[int(option)-1])))
        option2 = input('\tLoad which checkpoint? ')
        while not option2.isdigit() or int(option2)-1 not in range(n2):
             option2 = input('Invalid option. Type an integer 1 <= x <= {n}: '.format(n=n2))
        #end
        

        loadpath = 'training/{}/checkpoints/{}'.format(
            os.listdir('training')[int(option)-1],
            os.listdir('training/{}/checkpoints'.format(os.listdir('training')[int(option)-1]))[int(option2)-1]
            )

        print('Done! Load path: {}'.format(loadpath))

        print('\n-------------------------------------------\n')
    #end

    # Set RNG seed for Python, Numpy and Tensorflow
    random.seed(vars(args)['seed'])
    np.random.seed(vars(args)['seed'])
    tf.compat.v1.set_random_seed(vars(args)['seed'])

    # Setup parameters
    d                       = vars(args)['d']
    time_steps              = vars(args)['timesteps']
    dev                     = vars(args)['dev']
    epochs_n                = vars(args)['epochs']
    batch_size              = vars(args)['batchsize']
    load_checkpoints        = True if vars(args)['load_from'] is not None else vars(args)['load']
    save_checkpoints        = vars(args)['save']

    train_params = {
        'n_min': 20,
        'n_max': 40,
        'conn_min': vars(args)['cmin'],
        'conn_max': vars(args)['cmax'],
        'batches_per_epoch': 128,
        'samples': 2**15,
        'distances': vars(args)['distances']
    }

    test_params = {
        'n_min': train_params['n_min'],
        'n_max': train_params['n_max'],
        'conn_min': vars(args)['cmin'],
        'conn_max': vars(args)['cmax'],
        'batches_per_epoch': 32,
        'samples': 2**10,
        'distances': vars(args)['distances']
    }
    
    # Ensure that train and test datasets exist and create if inexistent
    ensure_datasets(batch_size, train_params, test_params)

    # Create train and test loaders
    train_loader    = InstanceLoader('instances/train')
    test_loader     = InstanceLoader('instances/test')

    # Build model
    print('Building model ...', flush=True)
    GNN = build_network(d)

    # Disallow GPU use
    # config = tf.compat.v1.ConfigProto(device_count = {'GPU':0})
    with tf.compat.v1.Session() as sess:

        # Initialize global variables
        print('Initializing global variables ... ', flush=True)
        sess.run( tf.compat.v1.global_variables_initializer() )

        # Restore saved weights
        if load_checkpoints: 
            start_epoch = load_weights(sess,loadpath)
        else:
            start_epoch = 0
        #end

        if not os.path.isdir('training'):
            os.makedirs('training')
        #end
        if not os.path.isdir('training/dev={dev}'.format(dev=dev)):
            os.makedirs('training/dev={dev}'.format(dev=dev))
        #end

        with open('training/dev={dev}/log.dat'.format(dev=dev),'a') as logfile:
            # Run for a number of epochs
            for epoch_i in np.arange(start_epoch, start_epoch + epochs_n):

                train_loader.reset()
                test_loader.reset()

                train_stats = { k:np.zeros(train_params['batches_per_epoch']) for k in ['loss','acc','sat','pred','TP','FP','TN','FN'] }
                test_stats = { k:np.zeros(test_params['batches_per_epoch']) for k in ['loss','acc','sat','pred','TP','FP','TN','FN'] }

                print('Training model...', flush=True)
                for (batch_i, batch) in islice(enumerate(train_loader.get_batches(batch_size, dev)), train_params['batches_per_epoch']):
                    train_stats['loss'][batch_i], train_stats['acc'][batch_i], train_stats['sat'][batch_i], train_stats['pred'][batch_i], train_stats['TP'][batch_i], train_stats['FP'][batch_i], train_stats['TN'][batch_i], train_stats['FN'][batch_i] = run_batch(sess, GNN, batch, batch_i, epoch_i, time_steps, train=True, verbose=True)
                #end
                summarize_epoch(epoch_i,train_stats['loss'],train_stats['acc'],train_stats['sat'],train_stats['pred'],train=True)

                print('Testing model...', flush=True)
                for (batch_i, batch) in islice(enumerate(test_loader.get_batches(batch_size, dev)), test_params['batches_per_epoch']):
                    test_stats['loss'][batch_i], test_stats['acc'][batch_i], test_stats['sat'][batch_i], test_stats['pred'][batch_i], test_stats['TP'][batch_i], test_stats['FP'][batch_i], test_stats['TN'][batch_i], test_stats['FN'][batch_i] = run_batch(sess, GNN, batch, batch_i, epoch_i, time_steps, train=False, verbose=True)
                #end
                summarize_epoch(epoch_i,test_stats['loss'],test_stats['acc'],test_stats['sat'],test_stats['pred'],train=False)

                # Save weights
                savepath = 'training/dev={dev}/checkpoints/epoch={epoch}'.format(dev=dev,epoch=int(round(100*np.ceil((epoch_i+1)/100))))
                os.makedirs(savepath, exist_ok=True)
                if save_checkpoints: save_weights(sess, savepath)

                logfile.write('{epoch_i} {trloss} {tracc} {trsat} {trpred} {trTP} {trFP} {trTN} {trFN} {tstloss} {tstacc} {tstsat} {tstpred} {tstTP} {tstFP} {tstTN} {tstFN}\n'.format(
                    
                    epoch_i = epoch_i,

                    trloss = np.mean(train_stats['loss']),
                    tracc = np.mean(train_stats['acc']),
                    trsat = np.mean(train_stats['sat']),
                    trpred = np.mean(train_stats['pred']),
                    trTP = np.mean(train_stats['TP']),
                    trFP = np.mean(train_stats['FP']),
                    trTN = np.mean(train_stats['TN']),
                    trFN = np.mean(train_stats['FN']),

                    tstloss = np.mean(test_stats['loss']),
                    tstacc = np.mean(test_stats['acc']),
                    tstsat = np.mean(test_stats['sat']),
                    tstpred = np.mean(test_stats['pred']),
                    tstTP = np.mean(train_stats['TP']),
                    tstFP = np.mean(train_stats['FP']),
                    tstTN = np.mean(train_stats['TN']),
                    tstFN = np.mean(train_stats['FN']),
                    )
                )
                logfile.flush()
            #end
        #end
    #end
#end
