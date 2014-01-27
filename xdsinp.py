#!/usr/bin/env python
import sys
import time
import os
import os.path
import socket
import re
from math import ceil
import logging
from logging.handlers import RotatingFileHandler
from jinja2 import FileSystemLoader
from flask import Flask, render_template, make_response, abort, request, g
import suds


try:
    import config
except ImportError:
    print 'Could not import configuration'

try:
    WS_URL = config.WS_URL
except (NameError, AttributeError):
    print 'No webservice URL in config, cannot continue'
    sys.exit(1)

ISPYB_USER = None
ISPYB_PASSWORD = None
try:
    ISPYB_USER = config.ISPYB_USER
    ISPYB_PASSWORD = config.ISPYB_PASSWORD
except (NameError, AttributeError):
    print 'No ispyb user, continuing without auth'

if ISPYB_PASSWORD is not None and ISPYB_USER is not None:
    SUDS_CLIENT_OPTS = {'username': ISPYB_USER, 'password': ISPYB_PASSWORD}
else:
    SUDS_CLIENT_OPTS = {}

REQUEST_TIMEOUT=3

app = Flask(__name__)
app.jinja_loader = FileSystemLoader([os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates")])
print os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates")


def file_template_to_xds(filename, wildcard_char='?'):
    # ispyb has the file template in python's old format string
    # format, XDS only has '?' wildcards. This converts stuff like
    # xqm2-grt36-03w1_1_%04d.img to xqm2-grt36-03w1_1_????.img. We
    # assume there can be only one occurence of the %d format
    # directive. Perhaps there is a more elegant way of doing
    # this.
    m = re.match('.+(?P<whole>%(?P<number>[0-9]+)d).*', filename)
    converted = '{before}{wildcard}{after}'.format(before=filename[0:m.start('whole')],
                                                   wildcard=wildcard_char*int(m.group('number')),
                                                   after=filename[m.end('whole'):])
    return converted


# helper function to calculate ranges
def calculate_spot_range(startimg, numimages, axisrange, degrees, middle=None):
    """Calculate spot ranges, one at the beginning and one at the end,
    plus an optional one in the middle, covering a given range.
    :param startimg: The start image number
    :param numimages: The number of images
    :param axisrange: The axis range
    :param degrees: How many degrees to cover
    :param middle: If not None, include a range in the middle"""

    # TODO: Some tests are missing (like overlapping ranges)

    res = []
    last_image = startimg + numimages - 1
    img_in_range = int(degrees / axisrange) - 1
    # Special case if we have few images: use the whole range
    if numimages < 20:
        return "{0} {1}".format(startimg, last_image)

    # first 5 degrees
    range_end = startimg + img_in_range
    # just in case
    if range_end > last_image:
        range_end = last_image
    res.append("{0} {1}".format(startimg, range_end))

    # optional middle range
    if middle is not None:
        middle_start = int(ceil(numimages / 2))
        middle_end = middle_start + img_in_range
        if middle_end > last_image:
            middle_end = last_image
        res.append("{0} {1}".format(middle_start, middle_end))

    # end range
    end_start = last_image - img_in_range - 1
    res.append("{0} {1}".format(end_start, last_image))

    return res


@app.route('/xds.inp/<int:dcid>')
def get_xds_inp(dcid):
    app.logger.debug('Generating XDS.INP for ID {0}'.format(dcid))
    t0=time.time()

    c = suds.client.Client(WS_URL, timeout=REQUEST_TIMEOUT, **SUDS_CLIENT_OPTS)
    res = c.service.getXDSInfo(dcid)

    reqtime = time.time()-t0
    gentime = time.strftime("%a, %d %b %Y %H:%M:%S")
    request_basedir = request.args.get("basedir")
    basedir = request.args.get("basedir", "../links")
    raw_data = request.args.get("basedir") is not None

    res.basedir = basedir
    res.request_basedir = request_basedir
    res.webservice_request_time = reqtime
    res.timestamp = gentime
    res.raw_data = raw_data

    file_template=res.fileTemplate
    converted = file_template_to_xds(file_template)
    res.fileTemplate = os.path.join(basedir, converted)
    try:
        sr_end = int((res.startImageNumber + res.numberOfImages - 1) / 2)
        sr_start = sr_end - int(3.0/res.axisRange)
        add_sr = [sr_start, sr_end]
        res.additionalSpotRange = "{0} {1}".format(sr_start, sr_end)
    except Exception:
        pass

    try:
        # The new spot ranges, for 5 and 10 degrees
        res.spotRange5 = calculate_spot_range(res.startImageNumber,
                                              res.numberOfImages,
                                              res.axisRange,
                                              5,
                                              middle=True)
        res.spotRange10 = calculate_spot_range(res.startImageNumber,
                                              res.numberOfImages,
                                              res.axisRange,
                                              10,
                                              middle=True)

    template_name = "xds_{0}_{1}.inp".format(res.detectorManufacturer.lower(), res.detectorModel.lower())
    response = make_response(render_template(template_name, data=res))
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/mosflm.inp/<int:dcid>')
def get_mosflm_inp(dcid):
    app.logger.debug('Generating mosflm.inp for ID {0}'.format(dcid))
    t0=time.time()

    c = suds.client.Client(WS_URL, timeout=REQUEST_TIMEOUT, **SUDS_CLIENT_OPTS)
    res = c.service.getXDSInfo(dcid)

    reqtime = time.time()-t0
    gentime = time.strftime("%a, %d %b %Y %H:%M:%S")
    basedir = request.args.get("basedir", "../links")

    res.webservice_request_time = reqtime
    res.timestamp = gentime

    file_template = res.fileTemplate
    res.fileTemplate = file_template_to_xds(file_template, wildcard_char='#')
    try:
        sr_end = int((res.startImageNumber + res.numberOfImages - 1) / 2)
        sr_start = sr_end - int(3.0/res.axisRange)
        add_sr = [sr_start, sr_end]
        res.additionalSpotRange = "{0} {1}".format(sr_start, sr_end)
    except Exception:
        pass

    template_name = "mosflm_{0}_{1}.inp".format(res.detectorManufacturer.lower(), res.detectorModel.lower())
    response = make_response(render_template(template_name, data=res))
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/stac.descr/<int:dcid>')
def get_stac_descr(dcid):
    app.logger.debug('Generating stac.descr for ID {0}'.format(dcid))

    c = suds.client.Client(WS_URL, timeout=REQUEST_TIMEOUT, **SUDS_CLIENT_OPTS)
    res = c.service.getXDSInfo(dcid)

    blname = os.environ.get('BEAMLINENAME')
    if blname is not None:
        templ = 'stac.descr.{0}'.format(blname)
    else:
        templ = 'stac.descr'
    response = make_response(render_template(templ, data=res))
    response.headers['Content-Type'] = 'text/plain'
    return response


@app.route('/def.site/<int:dcid>')
def get_def_site(dcid):
    app.logger.debug('Generating def.site for ID {0}'.format(dcid))
    t0=time.time()

    c = suds.client.Client(WS_URL, timeout=REQUEST_TIMEOUT, **SUDS_CLIENT_OPTS)
    res = c.service.getXDSInfo(dcid)

    reqtime = time.time()-t0
    gentime = time.strftime("%a, %d %b %Y %H:%M:%S")

    res.webservice_request_time = reqtime
    res.timestamp = gentime

    hostname = socket.gethostname()
    if hostname is not None:
        template_name = 'def.site.{0}'.format(hostname)
    else:
        template_name = 'def.site'
    response = make_response(render_template(template_name, data=res))
    response.headers['Content-Type'] = 'text/plain'
    return response


if __name__=='__main__':
    # setup the logfile
    my_dir = os.path.dirname(os.path.abspath(__file__))
    confpath = os.path.join(my_dir, 'logpath')
    if os.path.exists(confpath):
        with open(confpath) as f:
            logpath = os.path.expanduser(f.readline().strip())
        if os.path.isdir(logpath):
            handler = RotatingFileHandler(os.path.join(logpath, 'xdsinp.log'),
                                          backupCount=10,
                                          maxBytes=2048)
            fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(fmt)
            handler.setLevel(logging.DEBUG)
            app.logger.setLevel(logging.DEBUG)
            app.logger.addHandler(handler)
    app.run(host='0.0.0.0', port=int(sys.argv[1]))
