from datetime import datetime
import math
import os
from abc import ABCMeta, abstractmethod
import time

import netCDF4

import cablab


class CubeSourceProvider(metaclass=ABCMeta):
    """
    An abstract interface for objects represent data source providers for the data cube.
    Cube source providers are passed to the Cube.update() method.
    """

    @abstractmethod
    def prepare(self, cube_config):
        """
        Called by a Cube instance's update() method before any other provider methods are called.
        Provider instances should prepare themselves w.r.t. the given cube configuration.
        :param cube_config: The data cube config, instance of CubeConfig
        """
        pass

    @abstractmethod
    def get_temporal_coverage(self):
        """
        Return the start and end time of the available source data.
        :return: A tuple of datetime.datetime instances (start_time, end_time).
        """
        return None

    @abstractmethod
    def get_spatial_coverage(self):
        """
        Return the spatial coverage as a rectangle represented by a tuple (x, y, width, height) in the cube's image
        coordinates.
        :return: A tuple of integers (x, y, width, height) in the cube's image coordinates.
        """
        return None

    @abstractmethod
    def get_variable_metadata(self, variable):
        """
        Return a dictionary containing metadata for the given variable. The following metadata keys are mandatory:
        * 'datatype': The numpy datatype
        * ...
        :return: Variable metadata.
        """
        return None

    @abstractmethod
    def get_images(self, target_start_time, target_end_time):
        """
        Return a dictionary of variable names to image mappings where each image is a numpy array with the shape
        (height, width) derived from the self.get_spatial_coverage() method. The images must be computed (by
        aggregation or interpolation) from the source data in the temporal range target_start_time <= source_data_time
        < target_end_time and taking into account other data cube configuration settings.
        Called by a Cube instance's update() method for all possible time periods in the time range given by the
        self.get_temporal_coverage() method. The times given are adjusted w.r.t. the cube's start time and temporal
        resolution.

        :param: target_start_time The target start time as a datetime.datetime instance
        :param: target_end_time The target end time as a datetime.datetime instance
        :return: A dictionary variable_name --> image (numpy array of size (width, height)) or None if no such
        variables exists for the given target time range.
        """
        return None

    @abstractmethod
    def close(self):
        """
        Called by the cube's update() method after all images have been retrieved and the provider is no longer used.
        """
        pass


class BaseCubeSourceProvider(CubeSourceProvider):
    """
    A partial implementation of the CubeSourceProvider interface that computes its output image data
    using weighted averages. The weights are computed according to the overlap of source time ranges and a
    requested target time range.
    """

    def __init__(self):
        self.cube_config = None
        """ The cube's configuration. """
        self.source_time_ranges = []
        """ Sorted list of all time ranges of every source file. """

    def prepare(self, cube_config):
        """
        Stores the cube's configuration and calls self.get_source_time_ranges()
        whoese return value is also stored. Overrides should call the base class' method.
        """
        self.cube_config = cube_config
        self.source_time_ranges = self.get_source_time_ranges()

    @abstractmethod
    def get_source_time_ranges(self):
        """
        Return a sorted list of all time ranges of every source file.
        Items in this list must be 2-element tuples of datetime instances.
        """
        pass

    def get_temporal_coverage(self):
        """
        Return the temporal coverage derived from the value returned by self.get_source_time_ranges().
        """
        return self.source_time_ranges[0][0], self.source_time_ranges[-1][1]

    def get_images(self, target_start_time, target_end_time):
        """
        For each source time range that has an overlap with the given image time range compute a weight
        according to the overlapping range. Pass these weights as source index to weight mapping
        to self.compute_images_from_sources(index_to_weight) and return the result.
        """
        t1 = time.time()
        if len(self.source_time_ranges) == 0:
            return None
        index_to_weight = dict()
        for i in range(len(self.source_time_ranges)):
            source_start_time, source_end_time = self.source_time_ranges[i]
            weight = _get_overlap(source_start_time, source_end_time, target_start_time, target_end_time)
            if weight > 0:
                index_to_weight[i] = weight
        if not index_to_weight:
            return None
        self.log('computing images for time range %s to %s from %d source(s)...' % (target_start_time, target_end_time,
                                                                                    len(index_to_weight)))
        result = self.compute_images_from_sources(index_to_weight)

        t2 = time.time()
        self.log('images computed for %s, took %f seconds' % (str(list(result.keys())), t2 - t1))

        return result

    @abstractmethod
    def compute_images_from_sources(self, index_to_weight):
        """
        Compute the target images for all variables from the sources with the given time indices and weights.
        The time indices point into the list returned by self.get_source_time_ranges().
        The weights are float values computed from the overlap of source time ranges with a requested
        target time range.
        """
        pass

    @staticmethod
    def log(message):
        """
        Log a message.
        :param message: The message
        """
        print(message)


def _get_overlap(a1, a2, b1, b2):
    a1_in_range = b1 <= a1 <= b2
    a2_in_range = b1 <= a2 <= b2
    if a1_in_range and a2_in_range:
        return 1.0
    if a1_in_range:
        return (b2 - a1) / (b2 - b1)
    if a2_in_range:
        return (a2 - b1) / (b2 - b1)
    b1_in_range = a1 <= b1 <= a2
    b2_in_range = a1 <= b2 <= a2
    if b1_in_range and b2_in_range:
        return (b2 - b1) / (a2 - a1)
    return -1.0


class CubeConfig:
    """
    A data cube's static configuration information.

    >>> CubeConfig(2880, 1440)
    CubeConfig(2880, 1440, -180.0, -90.0, 0.25)
    """

    def __init__(self,
                 grid_width=1440,
                 grid_height=720,
                 easting=-180.0,
                 northing=-90.0,
                 spatial_res=0.25,
                 start_time=datetime(2000, 1, 1),
                 temporal_res=8,
                 variables=None,
                 format='NETCDF4_CLASSIC',
                 compression=False):
        """
        Create a configuration to be be used for creating new data cubes.

        :param grid_width: The fixed image width in pixels (longitude direction).
        :param grid_height: The fixed image height in pixels (latitude direction).
        :param easting: The longitude position of the lower-left-most corner of the lower-left-most image pixel.
        :param northing: The latitude position of the lower-left-most corner of the lower-left-most image pixel.
        :param spatial_res: The spatial image resolution in degree.
        :param start_time: The start time of the first image.
        :param temporal_res: The temporal resolution in days.
        :param variables: A list of variable names to be included in the cube.
        :param format: The data format used. Must be one of 'NETCDF4', 'NETCDF4_CLASSIC', 'NETCDF3_CLASSIC'
                       or 'NETCDF3_64BIT'.
        :param compression: Whether the data should be compressed.
        """

        self.grid_width = grid_width
        self.grid_height = grid_height
        self.easting = easting
        self.northing = northing
        self.spatial_res = spatial_res
        self.start_time = start_time
        self.temporal_res = temporal_res
        self.variables = variables
        self.format = format
        self.compression = compression

    def __repr__(self):
        return 'CubeConfig(%s, %s, %s, %s, %s)' % (
            self.grid_width, self.grid_height,
            self.easting, self.northing, self.spatial_res)

    @staticmethod
    def load(path):
        """
        Load a CubeConfig from a text file.
        :param path: The file's path name.
        :return: A new CubeConfig instance
        """
        config = CubeConfig()
        with open(path) as fp:
            code = fp.read()
            exec(code, {'datetime': __import__('datetime')}, config.__dict__)
        return config

    def store(self, path):
        """
        Store a CubeConfig in a text file.
        :param path: The file's path name.
        """
        with open(path, 'w') as fp:
            for name in self.__dict__:
                if not (name.startswith('_') or name.endswith('_')):
                    value = self.__dict__[name]
                    fp.write('%s = %s\n' % (name, repr(value)))


class Cube:
    """
    Represents an existing data cube.

    >>> Cube.create('/home/hans/mycube',CubeConfig())
    Cube(CubeConfig(1440, 720, -180.0, -90.0, 0.25), '/home/hans/mycube')
    """

    def __init__(self, base_dir, config):
        self.base_dir = base_dir
        self.config = config
        self.closed = False

    def __repr__(self):
        return 'Cube(%s, \'%s\')' % (self.config, self.base_dir)

    @staticmethod
    def open(base_dir):
        """
        Open an existing data cube. Use the Cube.update(provider) method to add data to the cube
        via a source data provider.

        :param base_dir: The data cube's base directory which must be empty or non-existent.
        :return: A cube instance.
        """

        if not os.path.exists(base_dir):
            raise IOError('data cube base directory does not exists: %s' % base_dir)
        config = CubeConfig.load(os.path.join(base_dir, 'cube.config'))
        return Cube(base_dir, config)

    @staticmethod
    def create(base_dir, config):
        """
        Create a new data cube. Use the Cube.update(provider) method to add data to the cube
        via a source data provider.

        :param base_dir: The data cube's base directory. Must not exists.
        :param config: The data cube's static information. Use an instance of CubeConfig.
        :return: A cube instance.
        """

        if os.path.exists(base_dir):
            raise IOError('data cube base directory exists: %s' % base_dir)
        os.mkdir(base_dir)
        config.store(os.path.join(base_dir, 'cube.config'))
        return Cube(base_dir, config)

    def close(self):
        """
        Closes the data cube.
        """
        self.closed = True

    def update(self, provider):
        """
        Updates the data cube with source data from the given image provider.
        :param provider: An instance of the abstract ImageProvider class
        """

        if self.closed:
            raise IOError('cube has been closed')

        provider.prepare(self.config)

        datasets = dict()

        cube_start_time = cablab.date2num(self.config.start_time)
        cube_temporal_res = self.config.temporal_res

        src_start_time, src_end_time = provider.get_temporal_coverage()
        src_start_time = cablab.date2num(src_start_time)
        src_end_time = cablab.date2num(src_end_time)

        # compute adjusted src_start_time
        n = _get_num_steps(cube_start_time, src_start_time, cube_temporal_res)
        src_start_time = cube_start_time + n * cube_temporal_res

        steps = _get_num_steps(src_start_time, src_end_time, cube_temporal_res)
        for i in range(steps + 1):
            target_start_time = src_start_time + i * cube_temporal_res
            target_end_time = src_start_time + (i + 1) * cube_temporal_res
            if target_start_time < src_end_time:
                target_time_range = (cablab.num2date(target_start_time), cablab.num2date(target_end_time))
                var_name_to_image = provider.get_images(*target_time_range)
                if var_name_to_image:
                    self._write_images(provider, datasets, target_time_range, var_name_to_image)

        for key in datasets:
            datasets[key].close()

        provider.close()

    def _write_images(self, provider, datasets, target_time_range, var_name_to_image):
        for var_name in var_name_to_image:
            image = var_name_to_image[var_name]
            if image is not None:
                self._write_image(provider, datasets, target_time_range, var_name, image)

    def _write_image(self, provider, datasets, target_time_range, var_name, image):
        target_start_time, target_end_time = target_time_range
        folder_name = var_name
        folder = os.path.join(os.path.join(self.base_dir, 'data', folder_name))
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        filename = '%04d_%s.nc' % (target_start_time.year, var_name)
        file = os.path.join(folder, filename)
        if filename in datasets:
            dataset = datasets[filename]
        else:
            if os.path.exists(file):
                dataset = netCDF4.Dataset(file, 'a')
            else:
                dataset = netCDF4.Dataset(file, 'w', format=self.config.format)
                self._init_variable_dataset(provider, dataset, var_name)
            datasets[filename] = dataset
        var_start_time = dataset.variables['start_time']
        var_end_time = dataset.variables['end_time']
        var_variable = dataset.variables[var_name]
        i = len(var_start_time)
        var_start_time[i] = cablab.date2num(target_start_time)
        var_end_time[i] = cablab.date2num(target_end_time)
        var_variable[i, :, :] = image

    def _init_variable_dataset(self, provider, dataset, var_name):

        image_x0, image_y0, image_width, image_height = provider.get_spatial_coverage()

        dataset.createDimension('time', None)
        dataset.createDimension('lat', image_height)
        dataset.createDimension('lon', image_width)

        var_start_time = dataset.createVariable('start_time', 'f8', ('time',))
        var_start_time.units = cablab.TIME_UNITS
        var_start_time.calendar = cablab.TIME_CALENDAR

        var_end_time = dataset.createVariable('end_time', 'f8', ('time',))
        var_end_time.units = cablab.TIME_UNITS
        var_end_time.calendar = cablab.TIME_CALENDAR

        var_longitude = dataset.createVariable('longitude', 'f4', ('lon',))
        var_longitude.units = 'degrees east'

        var_latitude = dataset.createVariable('latitude', 'f4', ('lat',))
        var_latitude.units = 'degrees north'

        spatial_res = self.config.spatial_res
        # reference: lower-left pixel of images, lower-left corner of pixel
        lon0 = self.config.easting + image_x0 * spatial_res
        for i in range(image_width):
            var_longitude[i] = lon0 + i * spatial_res
        # reference: upper-left pixel of images, lower-left corner of pixel
        lat0 = self.config.northing + (image_height - 1) * spatial_res
        for i in range(image_height):
            var_latitude[i] = lat0 - i * spatial_res

        # import time
        # dataset.source = 'CAB-LAB Software (module ' + __name__ + ')'
        # dataset.history = 'Created ' + time.ctime(time.time())
        # TODO: add more global attributes from CF-conventions here
        variable_metadata = provider.get_variable_metadata(var_name)
        var_variable = dataset.createVariable(var_name,
                                              variable_metadata['datatype'],
                                              ('time', 'lat', 'lon',),
                                              zlib=self.config.compression,
                                              fill_value=variable_metadata['fill_value'])
        var_variable.units = variable_metadata.get('units')
        var_variable.long_name = variable_metadata.get('long_name')
        var_variable.scale_factor = variable_metadata.get('scale_factor', 1.0)
        var_variable.add_offset = variable_metadata.get('add_offset', 0.0)
        # TODO: add more local attributes from CF-conventions here
        return dataset


def _get_num_steps(x1, x2, dx):
    return int(math.floor((x2 - x1) / dx))
