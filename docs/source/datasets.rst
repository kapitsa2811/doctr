doctr.datasets
==============

.. currentmodule:: doctr.datasets

Whether it is for training or for evaluation, having predefined objects to access datasets in your prefered framework
can be a significant save of time.


.. _datasets:

Available Datasets
------------------
The datasets from DocTR inherit from an abstract class that handles verified downloading from a given URL.

.. autoclass:: doctr.datasets.core.VisionDataset


Here are all datasets that are available through DocTR:

.. autoclass:: FUNSD
.. autoclass:: SROIE
.. autoclass:: CORD


Data Loading
------------
Each dataset has its specific way to load a sample, but handling batch aggregation and the underlying iterator is a task deferred to another object in DocTR.

.. autoclass:: doctr.datasets.loader.DataLoader


Supported Vocabs
----------------

Since textual content has to be encoded properly for models to interpret them efficiently, DocTR supports multiple sets
of vocabs.

.. autofunction:: encode_sequences
