import os
from datetime import datetime
import glob
import numpy
import re
import datetime as dt

from esdl.cube_provider import NetCDFCubeSourceProvider


class S1Provider(NetCDFCubeSourceProvider):

    def __init__(self, cube_config, name='sentinel1', dir=None, resampling_order=None, polarisation=None, orbit=None):
        super(S1Provider, self).__init__(
            cube_config, name, dir, resampling_order)
        self.old_indices = None
        self.pol = polarisation
        print(orbit)
        #if orbit not in ['A', 'D']:
        #    raise ValueError(
        #        "Orbit must be 'A' (ascending) or 'D' (descending).")
        self.orbit = orbit

    @property
    def variable_descriptors(self):
        return {
            'sentinel1_{0}_{1}'.format(self.pol.lower(), self.orbit.lower()): {
                'source_name': 'Band1',
                'data_type': numpy.float32,
                'fill_value': numpy.nan,
                'units': 'bsi',
                'long_name': 'Backscatter of Sentinel-1',
                'standard_name': 'bsi_{0}_{1}'.format(self.pol, self.orbit),
                'references': 'Copernicus Sentinel data 2018. Retrieved from '
                + 'Copernicus Open Access Hub 2018, processed by ESA.',
                'comment': '',
                'url': '',
                'project_name': 'Copernicus',
            }
        }

    def compute_source_time_ranges(self):
        print(self.dir_path)
        print(os.path.expanduser(self.dir_path))
        dir_path = os.path.realpath(os.path.expanduser(self.dir_path))
        # This assumes that orbit and polarisation are following each other in the filename
        globpattern = os.path.join(
            dir_path, "S1*_{0}_*{1}_*.nc".format(self.orbit, self.pol))
        file_paths = glob.glob(globpattern)
        print(globpattern)
        source_time_ranges = list()
        date_pattern = re.compile('(\\d{8}T\\d{6})')
        print(file_paths)

        for file_path in file_paths:
            dtstr = re.search(date_pattern, file_path).group()
            print(dtstr)
            t1 = datetime.strptime(dtstr, "%Y%m%dT%H%M%S")
            print(t1.tzinfo)
            t2 = t1 + dt.timedelta(hours=1)
            print(t2)

            source_time_ranges.append((t1, t2, file_path, None))

        return sorted(source_time_ranges, key=lambda item: item[0])

    def transform_source_image(self, source_image):
        """
        Transforms the source image, here by flipping and then shifting horizontally.
        :param source_image: 2D image
        :return: source_image
        """
        # TODO (hans-permana, 20161219): the following line is a workaround to an issue where the nan values are
        # always read as -9.9. Find out why these values are automatically
        # converted and create a better fix.
        source_image[source_image == -9.9] = numpy.nan

        return numpy.flipud(source_image)
