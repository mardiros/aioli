.. _instanciating_clients:

Instanciating Clients
=====================

After :ref:`registering resources<register_resources>` in blacksmith,
to consume API, a client must be instanciated.
To create a client, service has to be discoverable using a
:term:`service discovery` strategy, then resources can be consumed.

.. note::

   The :term:`service discovery` part will be covered later in the document,
   this chapter is about consuming resources.

To create a client, a :class:`blacksmith.AsyncClientFactory` object must be
configured, instanciated, then will be responsible to build client for every
registrated resources.

Synchronous code will use the :class:`blacksmith.SyncClientFactory` instead.

.. literalinclude:: instanciating_client_01.py

In the example above, we consume the previously registered resource ``item``,
from the service ``api`` at version ``None``.

The ``api.item`` property has methods **collection_get**, **collection_post**,
**get**, **patch**, **delete**, to name a few to consume registered api routes.
This section will be covered in the next section.

.. important::

   Only registered routes works, consuming an unregistered route in the contract
   will raise error at the runtime. See :ref:`register_resources`.

Type Hint
---------

For a better development experience, type hints can be added, like the
example bellow:


.. literalinclude:: instanciating_client_02.py

.. note::

   methods that consume API such as ``.get(param)`` in the exemple above,
   accept both form ``get({"id": item.id})`` and ``get(GetItem(id))``
   where ``GetItem`` is the Request Schema of the ``GET`` contract.

   The method accept a dict version of the request schema.


.. versionchanged:: 2.0

   Since blacksmith 2.0, responses are wrapped using the :term:`result library`.

   The collection class return a ``result.Result`` object, and the non collection,
   return a :class:`blacksmith.ResponseBox` that have the same mimic of the
   ``result.Result``. of the :term:`result library`.


Synchronous API
---------------

Resource registration does not change for the sync/async version, but,
all the runtime components differ. A prefix ``Async`` identified the
asynchronous version and the prefix ``Sync`` define the synchronous version.

Lastly, here is the same example, using the synchronous API.

.. literalinclude:: instanciating_client_03.py
