import os
from datetime import datetime
import glob
import netCDF4
import numpy
import re
import datetime as dt

from esdl.cube_provider import NetCDFCubeSourceProvider


class S1Provider(NetCDFCubeSourceProvider):
    def __init__(self, cube_config, name='sentinel1', dir=None, resampling_order=None, polarisation=None):
        super(S1Provider, self).__init__(cube_config, name, dir, resampling_order)
        self.old_indices = None
        self.pol = polarisation
    @property
    def variable_descriptors(self):
        return {
            'sentinel1_{}'.format(self.pol): {
                'source_name': 'Band1',
                'data_type': numpy.float32,
                'fill_value': numpy.nan,
                'units': 'bsi',
                'long_name': 'Backscatter of Sentinel-1',
                'standard_name': 'bsi_{}'.format(self.pol),
                'references': 'Laeng, A., et al. "The ozone climate change initiative: Comparison of four '
                              'Level-2 processors for the Michelson Interferometer for Passive Atmospheric '
                              'Sounding (MIPAS)." Remote Sensing of Environment 162 (2015): 316-343.',
                'comment': '',
                'url': '',
                'project_name' : 'Copernicus',
            }
        }

    def compute_source_time_ranges(self):
        file_names = glob.glob(self.dir_path + "/*" + self.pol + "*.nc")
        print(self.dir_path + "/*" + self.pol + "*.nc")
        source_time_ranges = list()
        date_pattern = re.compile('(\\d{8}T\\d{6})')
        print(file_names)
        for file_name in file_names:
            if file_name[-3:] != ".nc":
                continue
            file = os.path.join(self.dir_path, file_name)

            t1 = re.search(date_pattern, file_name).group()
            print(t1)
            dtobj = datetime.strptime(t1, "%Y%m%dT%H%M%S")
            print(dtobj.tzinfo)
            t2 = dtobj + dt.timedelta(hours=1)
            print(t2)

            source_time_ranges.append((dtobj,
                                       t2,
                                       file,
                                       None))
        return sorted(source_time_ranges, key=lambda item: item[0])

    def transform_source_image(self, source_image):
        """
        Transforms the source image, here by flipping and then shifting horizontally.
        :param source_image: 2D image
        :return: source_image
        """
        # TODO (hans-permana, 20161219): the following line is a workaround to an issue where the nan values are
        # always read as -9.9. Find out why these values are automatically converted and create a better fix.
        source_image[source_image == -9.9] = numpy.nan
        return numpy.roll(numpy.flipud(source_image), 180, axis=1)

def finder(dir=".", pattern=""):
    files = os.path.listdir(path)
