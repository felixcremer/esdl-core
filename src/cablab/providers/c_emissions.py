import os
from datetime import timedelta, datetime

import numpy

from cablab import NetCDFCubeSourceProvider


class CEmissionsProvider(NetCDFCubeSourceProvider):
    def __init__(self, cube_config, name='c_emissions', dir=None):
        super(CEmissionsProvider, self).__init__(cube_config, name, dir)
        self.old_indices = None

    @property
    def variable_descriptors(self):
        return {
            'c_emissions': {
                'source_name': 'Emission',
                'data_type': numpy.float32,
                'fill_value': -9999.0,
                'units': 'g C m-2 month-1',
                'long_name': 'CASA-GFED4 BB',
                'scale_factor': 1.0,
                'add_offset': 0.0,
            }
        }

    def compute_source_time_ranges(self):
        source_time_ranges = []
        file_names = os.listdir(self.dir_path)
        for file_name in file_names:
            file = os.path.join(self.dir_path, file_name)
            dates = [datetime(yr, mo, 1) for yr in range(2001, 2011) for mo in range(1, 13)]
            n = len(dates)
            for i in range(n):
                t1 = dates[i]
                if i < n - 1:
                    t2 = dates[i + 1]
                else:
                    t2 = t1 + timedelta(days=31)  # assuming it's December
                source_time_ranges.append((t1, t2, file, i))
        return sorted(source_time_ranges, key=lambda item: item[0])
