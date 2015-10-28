import os
from datetime import timedelta

import numpy
import netCDF4

from cablab import BaseCubeSourceProvider
from cablab.util import NetCDFDatasetCache

VAR_NAME = 'Precip'


class PrecipProvider(BaseCubeSourceProvider):
    def __init__(self, cube_config, dir_path):
        super(PrecipProvider, self).__init__(cube_config)
        if cube_config.grid_width != 1440 or cube_config.grid_height != 720:
            raise ValueError('illegal cube configuration, '
                             'provider does not yet implement proper spatial aggregation/interpolation')
        self.dir_path = dir_path
        self.source_time_ranges = None
        self.dataset_cache = NetCDFDatasetCache(VAR_NAME)
        self.old_indices = None

    def prepare(self):
        self._init_source_time_ranges()

    def get_variable_descriptors(self):
        return {
            VAR_NAME: {
                'data_type': numpy.float32,
                'fill_value': -9999.0,
                'units': 'mm/day',
                'long_name': 'Precip - V1.0',
                'standard_name': 'Precip',
                'scale_factor': 1.0,
                'add_offset': 0.0,
            }
        }

    def compute_variable_images_from_sources(self, index_to_weight):

        # close all datasets that wont be used anymore
        new_indices = set(index_to_weight.keys())
        if self.old_indices:
            unused_indices = self.old_indices - new_indices
            for i in unused_indices:
                file, time_index = self._get_file_and_time_index(i)
                self.dataset_cache.close_dataset(file)

        self.old_indices = new_indices

        if len(new_indices) == 1:
            i = next(iter(new_indices))
            file, time_index = self._get_file_and_time_index(i)
            dataset = self.dataset_cache.get_dataset(file)
            precip = numpy.kron(dataset.variables[VAR_NAME][time_index, :, :], numpy.ones((2, 2)))
        else:
            precip_sum = numpy.zeros((self.cube_config.grid_height, self.cube_config.grid_width),
                                     dtype=numpy.float32)
            weight_sum = 0.0
            for i in new_indices:
                weight = index_to_weight[i]
                file, time_index = self._get_file_and_time_index(i)
                dataset = self.dataset_cache.get_dataset(file)
                precip = dataset.variables[VAR_NAME]
                precip_sum += weight * numpy.kron(precip[time_index, :, :], numpy.ones((2, 2)))
                weight_sum += weight
            precip = precip_sum / weight_sum

        return {VAR_NAME: precip}

    def _get_file_and_time_index(self, i):
        return self.source_time_ranges[i][2:4]

    def get_source_time_ranges(self):
        return self.source_time_ranges

    def get_spatial_coverage(self):
        return 0, 0, 1440, 720

    def close(self):
        self.dataset_cache.close_all_datasets()

    def _init_source_time_ranges(self):
        source_time_ranges = []
        file_names = os.listdir(self.dir_path)
        for file_name in file_names:
            file = os.path.join(self.dir_path, file_name)
            dataset = self.dataset_cache.get_dataset(file)
            time = dataset.variables['time']
            dates = netCDF4.num2date(time[:], calendar=time.calendar, units=time.units)
            self.dataset_cache.close_dataset(file)
            source_time_ranges += [(dates[i], dates[i] + timedelta(days=1), file, i) for i in range(len(dates))]
        self.source_time_ranges = sorted(source_time_ranges, key=lambda item: item[0])