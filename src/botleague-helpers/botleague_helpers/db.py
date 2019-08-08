from __future__ import print_function

import random
import string
import sys
from typing import Any

from box import BoxList, Box

from botleague_helpers.config import blconfig
from botleague_helpers.config import get_test_name_from_callstack
from google.cloud import firestore

DEFAULT_COLLECTION = 'simple_key_value_store'


class DB:
    db = None
    collection = None

    def __init__(self, collection_name, use_boxes):
        self.collection_name = collection_name or DEFAULT_COLLECTION
        self.use_boxes = use_boxes

    def get(self, key):
        ret = self._get(key)
        ret = self._to_box(ret)
        return ret

    def set(self, key, value):
        value = self._from_box(value)
        self._set(key, value)

    def compare_and_swap(self, key, expected_current_value, new_value) -> bool:
        """
        Atomically update the key to the new value if the current value is the
        expected value.
        https://en.wikipedia.org/wiki/Compare-and-swap
        """
        new_value = self._from_box(new_value)
        expected_current_value = self._from_box(expected_current_value)
        return self._compare_and_swap(key, expected_current_value, new_value)

    def delete_all_test_data(self):
        raise NotImplementedError()

    def _compare_and_swap(self, key, expected_current_value, new_value) -> bool:
        raise NotImplementedError()

    def _get(self, key):
        raise NotImplementedError()

    def _set(self, key, value):
        raise NotImplementedError()

    def _from_box(self, value):
        if self.use_boxes:
            if isinstance(value, BoxList):
                value = value.to_list()
            elif isinstance(value, Box):
                value = value.to_dict()
        return value

    def _to_box(self, ret):
        if self.use_boxes:
            if isinstance(ret, list):
                ret = BoxList(ret)
            elif isinstance(ret, dict):
                ret = Box(ret)
        return ret


class DBFirestore(DB):
    def __init__(self, collection_name, use_boxes):
        super().__init__(collection_name, use_boxes)
        from firebase_admin import firestore
        blconfig.ensure_firebase_initialized()
        self.db = firestore.client()
        self.collection = self.db.collection(self.collection_name)

    def _get(self, key):
        value = self.collection.document(key).get().to_dict() or {}
        value = self._simplify_value(key, value)
        return value

    @staticmethod
    def _simplify_value(key, value):
        if value and key in value and len(value) == 1:
            # Document just contains the one field with the same name
            # as the document, so just return the value of the field.
            value = value[key]
        return value

    def _set(self, key, value):
        value = self._expand_value(key, value)
        self.collection.document(key).set(value)

    @staticmethod
    def _expand_value(key, value) -> Any:
        # Inverse of simplify value
        if not isinstance(value, dict):
            # Value is just a field
            ret = {key: value}
        else:
            # Value is a collection
            ret = value
        return ret

    def _compare_and_swap(self, key, expected_current_value, new_value) -> bool:
        ref = self.collection.document(key)
        transaction = self.db.transaction()

        @firestore.transactional
        def update_in_transaction(transaction_,
                                  ref_, expected_current_value_,
                                  new_value_) -> bool:
            """
            In the case of a concurrent edit, Cloud Firestore runs the
            entire transaction again. In this case the expected value will
            be different and set() will not be called, thus returning False.
            """
            snapshot = ref_.get(transaction=transaction_).to_dict()
            snapshot = self._simplify_value(key, snapshot)
            if snapshot == expected_current_value_:
                transaction_.set(ref_, self._expand_value(key, new_value_))
                ret_ = True
            else:
                ret_ = False
            return ret_

        ret = update_in_transaction(transaction, ref, expected_current_value,
                                    new_value)
        return ret

    def delete_all_test_data(self):
        if self.collection_name.startswith('test_'):
            delete_firestore_collection(self.collection)
            return True
        else:
            print('Not deleting collection %s whose name does not start with'
                  ' test_', file=sys.stderr)
            return False


def delete_firestore_collection(coll_ref, batch_size=10):
    # WARNING: Only do this for test data!
    # c.f. https://firebase.google.com/docs/firestore/solutions/delete-collections
    docs = coll_ref.limit(batch_size).get()
    deleted = 0

    for doc in docs:
        print(u'Deleting doc {} => {}'.format(doc.id, doc.to_dict()))
        doc.reference.delete()
        deleted = deleted + 1
    if deleted >= batch_size:
        return delete_firestore_collection(coll_ref, batch_size)


LOCAL_COLLECTIONS = {}


class DBLocal(DB):
    def __init__(self, collection_name, use_boxes):
        super().__init__(collection_name, use_boxes)
        self.collection = LOCAL_COLLECTIONS.setdefault(collection_name, {})

    def _get(self, key):
        return self.collection.get(key, None)

    def _set(self, key, value):
        self.collection[key] = value

    def _compare_and_swap(self, key, expected_current_value, new_value) -> bool:
        # Not threadsafe!
        if self.collection[key] == expected_current_value:
            self.collection[key] = new_value
            return True
        else:
            return False

    def delete_all_test_data(self):
        keys = list(LOCAL_COLLECTIONS.keys())
        for key in keys:
            del LOCAL_COLLECTIONS[key]


def get_db(collection_name: str = DEFAULT_COLLECTION,
           force_firestore_db=False,
           use_boxes=False) -> DB:
    """

    :param collection_name: Namespace for your db
    :param test_remote_db: For special cases where you want to test the db logic
    :param use_boxes: Return python-box objects instead of dicts / lists
    :return:
    """
    test_name = get_test_name_from_callstack()
    if test_name and not force_firestore_db:
        print('We are in a test, %s, so not using Firestore' % test_name)
        return DBLocal(collection_name, use_boxes)
    elif blconfig.should_use_firestore:
        print('Using Firestore backed key value store')
        return DBFirestore(collection_name, use_boxes)
    else:
        print('SHOULD_USE_FIRESTORE is false, so not using Firestore')
        return DBLocal(collection_name, use_boxes)
