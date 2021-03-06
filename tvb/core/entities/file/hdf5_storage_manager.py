# -*- coding: utf-8 -*-
#
#
# TheVirtualBrain-Framework Package. This package holds all Data Management, and 
# Web-UI helpful to run brain-simulations. To use it, you also need do download
# TheVirtualBrain-Scientific Package (for simulators). See content of the
# documentation-folder for more details. See also http://www.thevirtualbrain.org
#
# (c) 2012-2013, Baycrest Centre for Geriatric Care ("Baycrest")
#
# This program is free software; you can redistribute it and/or modify it under 
# the terms of the GNU General Public License version 2 as published by the Free
# Software Foundation. This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
# License for more details. You should have received a copy of the GNU General 
# Public License along with this program; if not, you can download it here
# http://www.gnu.org/licenses/old-licenses/gpl-2.0
#
#
#   CITATION:
# When using The Virtual Brain for scientific publications, please cite it as follows:
#
#   Paula Sanz Leon, Stuart A. Knock, M. Marmaduke Woodman, Lia Domide,
#   Jochen Mersmann, Anthony R. McIntosh, Viktor Jirsa (2013)
#       The Virtual Brain: a simulator of primate brain network dynamics.
#   Frontiers in Neuroinformatics (7:10. doi: 10.3389/fninf.2013.00010)
#
#
"""
Persistence of data in HDF5 format.

.. moduleauthor:: Lia Domide <lia.domide@codemart.ro>
.. moduleauthor:: Bogdan Neacsa <bogdan.neacsa@codemart.ro>
.. moduleauthor:: Calin Pavel <calin.pavel@codemart.ro>
"""

import os
import copy
import threading
import h5py as hdf5
import numpy as numpy
import tvb.core.utils as utils
from datetime import datetime
from tvb.basic.logger.builder import get_logger
from tvb.basic.profile import TvbProfile
from tvb.core.entities.file.exceptions import FileStructureException, MissingDataSetException
from tvb.core.entities.file.exceptions import IncompatibleFileManagerException, MissingDataFileException
from tvb.core.entities.transient.structure_entities import GenericMetaData


# Create logger for this module
LOG = get_logger(__name__)

LOCK_OPEN_FILE = threading.Lock()

## The chunk block size recommended by h5py should be between 10k - 300k, larger for
## big files. Since performance will mostly be important for the simulator we'll just use the top range for now.
CHUNK_BLOCK_SIZE = 300000


class HDF5StorageManager(object):
    """
    This class is responsible for saving / loading data in HDF5 file / format.
    """
    __file_title_ = "TVB data file"
    __storage_full_name = None
    __hfd5_file = None

    TVB_ATTRIBUTE_PREFIX = "TVB_"
    ROOT_NODE_PATH = "/"
    BOOL_VALUE_PREFIX = "bool:"
    DATETIME_VALUE_PREFIX = "datetime:"
    DATE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
    LOCKS = {}


    def __init__(self, storage_folder, file_name, buffer_size=600000):
        """
        Creates a new storage manager instance.
        :param buffer_size: the size in Bytes of the amount of data that will be buffered before writing to file.
        """
        if storage_folder is None:
            raise FileStructureException("Please provide the folder where to store data")
        if file_name is None:
            raise FileStructureException("Please provide the file name where to store data")
        self.__storage_full_name = os.path.join(storage_folder, file_name)
        self.__buffer_size = buffer_size
        self.__buffer_array = None
        self.data_buffers = {}


    def is_valid_hdf5_file(self):
        """
        This method checks if specified file exists and if it has correct HDF5 format
        :returns: True is file exists and has HDF5 format. False otherwise.
        """
        try:
            return os.path.exists(self.__storage_full_name) and hdf5.h5f.is_hdf5(self.__storage_full_name)
        except RuntimeError:
            return False


    def store_data(self, dataset_name, data_list, where=ROOT_NODE_PATH):
        """
        This method stores provided data list into a data set in the H5 file.
        
        :param dataset_name: Name of the data set where to store data
        :param data_list: Data to be stored
        :param where: represents the path where to store our dataset (e.g. /data/info)
        """
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH

        data_to_store = self._check_data(data_list)

        try:
            LOG.debug("Saving data into data set: %s" % dataset_name)
            chunk_shape = self.__compute_chunk_shape(data_to_store.shape)

            # Open file in append mode ('a') to allow adding multiple data sets in the same file
            hdf5File = self._open_h5_file(chunk_shape=chunk_shape)

            full_dataset_name = where + dataset_name
            if full_dataset_name not in hdf5File:
                hdf5File.create_dataset(full_dataset_name, data=data_to_store)

            elif hdf5File[full_dataset_name].shape == data_to_store.shape:
                hdf5File[full_dataset_name][...] = data_to_store[...]

            else:
                raise IncompatibleFileManagerException("Cannot update existing H5 DataSet %s with a different shape. "
                                                       "Try defining it as chunked!" % full_dataset_name)

        finally:
            # Now close file
            self.close_file()


    def append_data(self, dataset_name, data_list, grow_dimension=-1, close_file=True, where=ROOT_NODE_PATH):
        """
        This method appends data to an existing data set. If the data set does not exists, create it first.
        
        :param dataset_name: Name of the data set where to store data
        :param data_list: Data to be stored / appended
        :param grow_dimension: The dimension to be used to grow stored array. By default will grow on the LAST dimension
        :param close_file: Specify if the file should be closed automatically after write operation. If not, 
            you have to close file by calling method close_file()
        :param where: represents the path where to store our dataset (e.g. /data/info)
        
        """
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH
        data_to_store = self._check_data(data_list)
        data_buffer = self.data_buffers.get(where + dataset_name, None)

        if data_buffer is None:
            chunk_shape = self.__compute_chunk_shape(data_to_store.shape, grow_dimension)
            hdf5File = self._open_h5_file(chunk_shape=chunk_shape)
            datapath = where + dataset_name
            if datapath in hdf5File:
                dataset = hdf5File[datapath]
                self.data_buffers[datapath] = HDF5StorageManager.H5pyStorageBuffer(dataset,
                                                                                   buffer_size=self.__buffer_size,
                                                                                   buffered_data=data_to_store,
                                                                                   grow_dimension=grow_dimension)
            else:
                data_shape_list = list(data_to_store.shape)
                data_shape_list[grow_dimension] = None
                data_shape = tuple(data_shape_list)
                dataset = hdf5File.create_dataset(where + dataset_name, data=data_to_store, shape=data_to_store.shape,
                                                  dtype=data_to_store.dtype, maxshape=data_shape)
                self.data_buffers[datapath] = HDF5StorageManager.H5pyStorageBuffer(dataset,
                                                                                   buffer_size=self.__buffer_size,
                                                                                   buffered_data=None,
                                                                                   grow_dimension=grow_dimension)
        else:
            if not data_buffer.buffer_data(data_to_store):
                data_buffer.flush_buffered_data()
        if close_file:
            self.close_file()


    def remove_data(self, dataset_name, where=ROOT_NODE_PATH):
        """
        Deleting a data set from H5 file.
        
        :param dataset_name:name of the data set to be deleted
        :param where: represents the path where dataset is stored (e.g. /data/info)
          
        """
        LOG.debug("Removing data set: %s" % dataset_name)
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH
        try:
            # Open file in append mode ('a') to allow data remove
            hdf5File = self._open_h5_file()
            del hdf5File[where + dataset_name]

        except KeyError:
            LOG.warn("Trying to delete data set: %s but current file does not contain it." % dataset_name)
            raise FileStructureException("Could not locate dataset: %s" % dataset_name)
        finally:
            self.close_file()


    def get_data(self, dataset_name, data_slice=None, where=ROOT_NODE_PATH, ignore_errors=False):
        """
        This method reads data from the given data set based on the slice specification
        
        :param dataset_name: Name of the data set from where to read data
        :param data_slice: Specify how to retrieve data from array {e.g (slice(1,10,1),slice(1,6,2)) }
        :param where: represents the path where dataset is stored (e.g. /data/info)  
        :returns: a numpy.ndarray containing filtered data
        
        """
        LOG.debug("Reading data from data set: %s" % dataset_name)
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH

        datapath = where + dataset_name
        try:
            # Open file to read data
            hdf5File = self._open_h5_file('r')
            if datapath in hdf5File:
                data_array = hdf5File[datapath]
                # Now read data
                if data_slice is None:
                    return data_array[()]
                else:
                    return data_array[data_slice]
            else:
                if not ignore_errors:
                    LOG.error("Trying to read data from a missing data set: %s" % dataset_name)
                    raise MissingDataSetException("Could not locate dataset: %s" % dataset_name)
                else:
                    return numpy.ndarray(0)
        finally:
            self.close_file()


    def get_data_shape(self, dataset_name, where=ROOT_NODE_PATH, ignore_errors=False):
        """
        This method reads data-size from the given data set 
        
        :param dataset_name: Name of the data set from where to read data
        :param where: represents the path where dataset is stored (e.g. /data/info)  
        :returns: a tuple containing data size
        
        """
        LOG.debug("Reading data from data set: %s" % dataset_name)
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH

        try:
            # Open file to read data
            hdf5File = self._open_h5_file('r')
            data_array = hdf5File[where + dataset_name]
            return data_array.shape
        except KeyError:
            if not ignore_errors:
                LOG.debug("Trying to read data from a missing data set: %s" % dataset_name)
                raise MissingDataSetException("Could not locate dataset: %s" % dataset_name)
            else:
                return 0
        finally:
            self.close_file()


    def set_metadata(self, meta_dictionary, dataset_name='', tvb_specific_metadata=True, where=ROOT_NODE_PATH):
        """
        Set meta-data information for root node or for a given data set.
        
        :param meta_dictionary: dictionary containing meta info to be stored on node
        :param dataset_name: name of the dataset where to assign metadata. If None, metadata is assigned to ROOT node.
        :param tvb_specific_metadata: specify if the provided metadata is TVB specific (All keys will have a TVB prefix)
        :param where: represents the path where dataset is stored (e.g. /data/info)     
        
        """
        LOG.debug("Setting metadata on node: %s" % dataset_name)
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH

        # Open file to read data
        hdf5File = self._open_h5_file()
        try:
            node = hdf5File[where + dataset_name]
        except KeyError:
            LOG.debug("Trying to set metadata on a missing data set: %s" % dataset_name)
            node = hdf5File.create_dataset(where + dataset_name, (1,))

        try:
            # Now set meta-data
            for meta_key in meta_dictionary:
                key_to_store = meta_key
                if tvb_specific_metadata:
                    key_to_store = self.TVB_ATTRIBUTE_PREFIX + meta_key

                processed_value = self._serialize_value(meta_dictionary[meta_key])
                node.attrs[key_to_store] = processed_value
        finally:
            self.close_file()


    def _serialize_value(self, value):
        """
        This method takes a value which will be stored as metadata and 
        apply some transformation if necessary
        
        :param value: value which is planned to be stored
        :returns:  value to be stored
        
        """
        if value is None:
            return ''
        # Force unicode strings to simple strings.
        if isinstance(value, unicode):
            return str(value)
        # Transform boolean to string and prefix it
        elif isinstance(value, bool):
            return self.BOOL_VALUE_PREFIX + str(value)
        # Transform date to string and append prefix
        elif isinstance(value, datetime):
            return self.DATETIME_VALUE_PREFIX + utils.date2string(value, date_format=self.DATE_TIME_FORMAT)
        else:
            return value


    def remove_metadata(self, meta_key, dataset_name='', tvb_specific_metadata=True, where=ROOT_NODE_PATH):
        """
        Remove meta-data information for root node or for a given data set.
        
        :param meta_key: name of the metadata attribute to be removed
        :param dataset_name: name of the dataset from where to delete metadata. 
            If None, metadata will be removed from ROOT node.
        :param tvb_specific_metadata: specify if the provided metadata is specific to TVB (keys will have a TVB prefix).
        :param where: represents the path where dataset is stored (e.g. /data/info)
             
        """
        LOG.debug("Deleting metadata: %s for dataset: %s" % (meta_key, dataset_name))
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH
        try:
            # Open file to read data
            hdf5File = self._open_h5_file()
            node = hdf5File[where + dataset_name]

            # Now delete metadata
            key_to_remove = meta_key
            if tvb_specific_metadata:
                key_to_remove = self.TVB_ATTRIBUTE_PREFIX + meta_key
            del node.attrs[key_to_remove]
        except KeyError:
            LOG.error("Trying to delete metadata on a missing data set: %s" % dataset_name)
            raise FileStructureException("Could not locate dataset: %s" % dataset_name)
        except AttributeError:
            LOG.error("Trying to delete missing metadata %s" % meta_key)
            raise FileStructureException("There is no metadata named %s on this node" % meta_key)
        finally:
            self.close_file()


    def get_metadata(self, dataset_name='', where=ROOT_NODE_PATH, ignore_errors=False):
        """
        Retrieve ALL meta-data information for root node or for a given data set.
        
        :param dataset_name: name of the dataset for which to read metadata. If None, read metadata from ROOT node.
        :param where: represents the path where dataset is stored (e.g. /data/info)  
        :returns: a dictionary containing all metadata associated with the node
        
        """
        LOG.debug("Retrieving metadata for dataset: %s" % dataset_name)
        if dataset_name is None:
            dataset_name = ''
        if where is None:
            where = self.ROOT_NODE_PATH

        meta_key = ""
        try:
            # Open file to read data
            hdf5File = self._open_h5_file('r')
            node = hdf5File[where + dataset_name]
            # Now retrieve metadata values
            all_meta_data = {}

            for meta_key in node.attrs:
                new_key = meta_key
                if meta_key.startswith(self.TVB_ATTRIBUTE_PREFIX):
                    new_key = meta_key[len(self.TVB_ATTRIBUTE_PREFIX):]
                value = node.attrs[meta_key]
                all_meta_data[new_key] = self._deserialize_value(value)
            return all_meta_data

        except KeyError:
            if not ignore_errors:
                msg = "Trying to read data from a missing data set: %s" % (where + dataset_name)
                LOG.warning(msg)
                raise MissingDataSetException(msg)
            else:
                return numpy.ndarray(0)
        except AttributeError:
            msg = "Trying to get value for missing metadata %s" % meta_key
            LOG.error(msg)
            raise FileStructureException(msg)
        except Exception, excep:
            msg = "Failed to read metadata from H5 file! %s" % self.__storage_full_name
            LOG.exception(excep)
            LOG.error(msg)
            raise FileStructureException(msg)
        finally:
            self.close_file()


    def get_file_data_version(self):
        """
        Checks the data version for the current file.
        """
        if not os.path.exists(self.__storage_full_name):
            raise MissingDataFileException("File storage data not found at path %s" % (self.__storage_full_name,))

        if self.is_valid_hdf5_file():
            metadata = self.get_metadata()
            data_version = TvbProfile.current.version.DATA_VERSION_ATTRIBUTE
            if data_version in metadata:
                return metadata[data_version]
            else:
                raise IncompatibleFileManagerException("Could not find TVB specific data version attribute %s in file: "
                                                       "%s." % (data_version, self.__storage_full_name))
        raise IncompatibleFileManagerException("File %s is not a hdf5 format file. Are you using the correct "
                                               "manager for this file?" % (self.__storage_full_name,))


    def get_gid_attribute(self):
        """
        Used for obtaining the gid of the DataType of
        which data are stored in the current file.
        """
        if self.is_valid_hdf5_file():
            metadata = self.get_metadata()
            if GenericMetaData.KEY_GID in metadata:
                return metadata[GenericMetaData.KEY_GID]
            else:
                raise IncompatibleFileManagerException("Could not find the Gid attribute in the "
                                                       "input file %s." % self.__storage_full_name)
        raise IncompatibleFileManagerException("File %s is not a hdf5 format file. Are you using the correct "
                                               "manager for this file?" % (self.__storage_full_name,))


    def _deserialize_value(self, value):
        """
        This method takes value loaded from H5 file and transform it to TVB data. 
        """
        if value is not None:
            if isinstance(value, numpy.string_):
                if len(value) == 0:
                    value = None
                else:
                    value = str(value)

            if isinstance(value, str):
                if value.startswith(self.BOOL_VALUE_PREFIX):
                    # Remove bool prefix and transform to bool
                    return utils.string2bool(value[len(self.BOOL_VALUE_PREFIX):])
                if value.startswith(self.DATETIME_VALUE_PREFIX):
                    # Remove datetime prefix and transform to datetime
                    return utils.string2date(value[len(self.DATETIME_VALUE_PREFIX):], date_format=self.DATE_TIME_FORMAT)

        return value


    def __aquire_lock(self):
        """
        Aquire a unique lock for each different file path on the system.
        """
        lock = self.LOCKS.get(self.__storage_full_name, None)
        if lock is None:
            lock = threading.Lock()
            self.LOCKS[self.__storage_full_name] = lock
        lock.acquire()


    def __release_lock(self):
        """
        Aquire a unique lock for each different file path on the system.
        """
        lock = self.LOCKS.get(self.__storage_full_name, None)
        if lock is None:
            raise Exception("Some lock was deleted without being released beforehand.")
        lock.release()


    def close_file(self):
        """
        The synchronization of open/close doesn't seem to be needed anymore for h5py in
        contrast to PyTables for concurrent reads. However since it shouldn't add that
        much overhead in most situation we'll leave it like this for now since in case
        of concurrent writes(metadata) this provides extra safety.
        """
        try:
            self.__aquire_lock()
            self.__close_file()
        finally:
            self.__release_lock()


    def _open_h5_file(self, mode='a', chunk_shape=None):
        """
        The synchronization of open/close doesn't seem to be needed anymore for h5py in
        contrast to PyTables for concurrent reads. However since it shouldn't add that
        much overhead in most situation we'll leave it like this for now since in case
        of concurrent writes(metadata) this provides extra safety.
        """
        try:
            self.__aquire_lock()
            file_obj = self.__open_h5_file(mode, chunk_shape)
        finally:
            self.__release_lock()
        return file_obj


    def __compute_chunk_shape(self, data_shape, grow_dim=None):
        data_shape = list(data_shape)
        if not data_shape:
            return 1
        nr_elems_per_block = CHUNK_BLOCK_SIZE / 8.0
        if grow_dim is None:
            # We don't know what dimension is growing or we are not in
            # append mode and just want to write the whole data.
            max_leng_dim = data_shape.index(max(data_shape))
            for dim in data_shape:
                if dim != 0:
                    nr_elems_per_block = nr_elems_per_block / dim
            nr_elems_per_block = nr_elems_per_block * data_shape[max_leng_dim]
            if nr_elems_per_block < 1:
                nr_elems_per_block = 1
            data_shape[max_leng_dim] = int(nr_elems_per_block)
            return tuple(data_shape)
        else:
            for idx, dim in enumerate(data_shape):
                if idx != grow_dim and dim != 0:
                    nr_elems_per_block = nr_elems_per_block / dim
            if nr_elems_per_block < 1:
                nr_elems_per_block = 1
            data_shape[grow_dim] = int(nr_elems_per_block)
            return tuple(data_shape)


    def __close_file(self):
        """
        Close file used to store data.
        """
        hdf5_file = self.__hfd5_file

        # Try to close file only if it was opened before
        if hdf5_file is not None and hdf5_file.fid.valid:
            LOG.debug("Closing file: %s" % self.__storage_full_name)
            try:
                for h5py_buffer in self.data_buffers.values():
                    h5py_buffer.flush_buffered_data()
                self.data_buffers = {}
                hdf5_file.close()
            except Exception, excep:
                ### Do nothing is this situation.
                ### The file is correctly closed, but the list of open files on HDF5 is not updated in a synch manner.
                ### del _open_files[filename] might throw KeyError
                LOG.exception(excep)
            if not hdf5_file.fid.valid:
                self.__hfd5_file = None


    # -------------- Private methods  --------------
    def __open_h5_file(self, mode='a', chunk_shape=None):
        """
        Open file for reading, writing or append. 
        
        :param mode: Mode to open file (possible values are w / r / a).
                    Default value is 'a', to allow adding multiple data to the same file.
        :param chunk_shape: Shape for chunks at write.
        :returns: returns the file which stores data in HDF5 format opened for read / write according to mode param
        
        """
        if self.__storage_full_name is None:
            raise FileStructureException("Invalid storage file. Please provide a valid path.")
        try:
            # Check if file is still open from previous writes.
            if self.__hfd5_file is None or not self.__hfd5_file.fid.valid:
                file_exists = os.path.exists(self.__storage_full_name)

                # bug in some versions of hdf5 on windows prevent creating file with mode='a'
                if not file_exists and mode == 'a':
                    mode = 'w'

                LOG.debug("Opening file: %s in mode: %s" % (self.__storage_full_name, mode))
                self.__hfd5_file = hdf5.File(self.__storage_full_name, mode, libver='latest', chunks=chunk_shape)

                # If this is the first time we access file, write data version
                if not file_exists:
                    os.chmod(self.__storage_full_name, TvbProfile.current.ACCESS_MODE_TVB_FILES)
                    self.__hfd5_file['/'].attrs[self.TVB_ATTRIBUTE_PREFIX +
                            TvbProfile.current.version.DATA_VERSION_ATTRIBUTE] = TvbProfile.current.version.DATA_VERSION
        except (IOError, OSError), err:
            LOG.exception("Could not open storage file.")
            raise FileStructureException("Could not open storage file. %s" % err)

        return self.__hfd5_file



    def _check_data(self, data_list):
        """
        Check if the data to be stores is in a good format. If not adapt it.
        """
        if data_list is None:
            raise FileStructureException("Could not store null data")

        if not (isinstance(data_list, list) or isinstance(data_list, numpy.ndarray)):
            raise FileStructureException("Invalid data type. Could not store data of type:" + str(type(data_list)))

        data_to_store = data_list
        if isinstance(data_to_store, list):
            data_to_store = numpy.array(data_list)
        return data_to_store



    class H5pyStorageBuffer():
        """
        Helper class in order to buffer data for append operations, to limit the number of actual
        HDD I/O operations.
        """

        def __init__(self, h5py_dataset, buffer_size=300, buffered_data=None, grow_dimension=-1):
            self.buffered_data = buffered_data
            self.buffer_size = buffer_size
            if h5py_dataset is None:
                raise MissingDataSetException("A H5pyStorageBuffer instance must have a h5py dataset for which the"
                                              "buffering is done. Please supply one to the 'h5py_dataset' parameter.")
            self.h5py_dataset = h5py_dataset
            self.grow_dimension = grow_dimension

        def buffer_data(self, data_list):
            """
            Add data_list to an internal buffer in order to improve performance for append_data type of operations.
            :returns: True if buffer is still fine, \
                      False if a flush is necessary since the buffer is full
            """
            if self.buffered_data is None:
                self.buffered_data = data_list
            else:
                self.buffered_data = self.__custom_numpy_append(self.buffered_data, data_list)
            if self.buffered_data.nbytes > self.buffer_size:
                return False
            else:
                return True


        def __custom_numpy_append(self, array1, array2):
            array_1_shape = numpy.array(array1.shape)
            array_2_shape = numpy.array(array2.shape)
            result_shape = copy.deepcopy(array_1_shape)
            result_shape[self.grow_dimension] += array_2_shape[self.grow_dimension]
            result_array = numpy.empty(shape=tuple(result_shape), dtype=array1.dtype)
            full_slice = slice(None, None, None)
            full_index = [full_slice for _ in array_1_shape]
            full_index[self.grow_dimension] = slice(0, array_1_shape[self.grow_dimension], None)
            result_array[tuple(full_index)] = array1
            full_index[self.grow_dimension] = slice(array_1_shape[self.grow_dimension],
                                                    result_shape[self.grow_dimension], None)
            result_array[tuple(full_index)] = array2
            return result_array


        def flush_buffered_data(self):
            """
            Append the data buffered so far to the input dataset using :param grow_dimension: as the dimension that
            will be expanded. 
            """
            if self.buffered_data is not None:
                current_shape = self.h5py_dataset.shape
                new_shape = list(current_shape)
                new_shape[self.grow_dimension] += self.buffered_data.shape[self.grow_dimension]
                ## Create the required slice to which the new data will be added.
                ## For example if the 3nd dimension of a 4D datashape (74, 1, 100, 1)
                ## we want to get the slice (:, :, 100:200, :) in order to add 100 new entries
                full_slice = slice(None, None, None)
                slice_to_add = slice(current_shape[self.grow_dimension], new_shape[self.grow_dimension], None)
                appendTo_address = [full_slice for _ in new_shape]
                appendTo_address[self.grow_dimension] = slice_to_add
                ## Do the data reshape and copy the new data
                self.h5py_dataset.resize(tuple(new_shape))
                self.h5py_dataset[tuple(appendTo_address)] = self.buffered_data
                self.buffered_data = None

