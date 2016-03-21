from datetime import datetime, timedelta
import os

import numpy
import netCDF4

from cablab import BaseCubeSourceProvider
from cablab.util import NetCDFDatasetCache, aggregate_images

VAR_NAME = 'SWE'


class SnowWaterEquivalentProvider(BaseCubeSourceProvider):
    def __init__(self, cube_config, dir_path):
        super(SnowWaterEquivalentProvider, self).__init__(cube_config)
        # todo (nf 20151028) - remove check once we have addressed spatial aggregation/interpolation, see issue #3
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
                'units': 'mm',
                'long_name': 'Daily Snow Water Equivalent',
                'scale_factor': 1.0,
                'add_offset': 0.0,
                'certain_values': "-2 == mountains, -1 == water bodies, 0 == either SWE, "
                                  "or missing data in the southern hemisphere",
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
            swe = dataset.variables[VAR_NAME][time_index, :, :]
        else:
            images = [None] * len(new_indices)
            weights = [None] * len(new_indices)
            j = 0
            for i in new_indices:
                file, time_index = self._get_file_and_time_index(i)
                dataset = self.dataset_cache.get_dataset(file)
                variable = dataset.variables[VAR_NAME]
                images[j] = variable[time_index, :, :]
                weights[j] = index_to_weight[i]
                j += 1
            swe = aggregate_images(images, weights=weights)

        return {VAR_NAME: swe}

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
            time_bnds = dataset.variables['time']
            time = netCDF4.num2date(time_bnds[:], 'days since 1582-10-15 00:00', calendar='gregorian')
            self.dataset_cache.close_dataset(file)
            for i in range(len(time)):
                t1 = datetime(time[i].year, time[i].month, time[i].day)
                t2 = t1 + timedelta(days=1)
                source_time_ranges.append((t1, t2, file, i))
        self.source_time_ranges = sorted(source_time_ranges, key=lambda item: item[0])