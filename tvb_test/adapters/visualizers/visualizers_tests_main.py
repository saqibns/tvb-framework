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
#   Frontiers in Neuroinformatics (in press)
#
#

"""
.. moduleauthor:: Bogdan Neacs <lia.domide@codemart.ro>
"""

import unittest
from tvb_test.adapters.visualizers import brainviewer_test
from tvb_test.adapters.visualizers import connectivityviewer_test
from tvb_test.adapters.visualizers import covarianceviewer_test
from tvb_test.adapters.visualizers import crosscoherenceviewer_test
from tvb_test.adapters.visualizers import crosscorelationviewer_test
from tvb_test.adapters.visualizers import eegmonitor_test
from tvb_test.adapters.visualizers import ica_test
from tvb_test.adapters.visualizers import pse_test
from tvb_test.adapters.visualizers import time_series_test


def suite():
    """
    Gather all the tests in package 'adapters' in a test suite.
    """
    test_suite = unittest.TestSuite()
    test_suite.addTest(brainviewer_test.suite())
    test_suite.addTest(connectivityviewer_test.suite())
    test_suite.addTest(covarianceviewer_test.suite())
    test_suite.addTest(crosscoherenceviewer_test.suite())
    test_suite.addTest(crosscorelationviewer_test.suite())
    test_suite.addTest(eegmonitor_test.suite())
    test_suite.addTest(ica_test.suite())
    test_suite.addTest(pse_test.suite())
    test_suite.addTest(time_series_test.suite())
#    test_suite.addTest(histogram_test.suite())
    return test_suite


if __name__ == "__main__":
    #So you can run tests from this package individually.
    TEST_RUNNER = unittest.TextTestRunner()
    TEST_SUITE = suite()
    TEST_RUNNER.run(TEST_SUITE)
    
    
