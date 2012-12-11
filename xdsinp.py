#!/usr/bin/env python
import sys
import time
import os
import os.path
from jinja2 import FileSystemLoader
from flask import Flask, render_template, make_response, abort, request, g
import suds
import re
import logging
from logging.handlers import RotatingFileHandler

WSDL_URL='http://pyprocz.esrf.fr:8080/ispyb-ejb3/ispybWS/ToolsForCollectionWebService?wsdl'
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

@app.before_request
def before_request():
    if not hasattr(g, 'getXDSInfo'):
        g.getXDSInfo = suds.client.Client(WSDL_URL, timeout=REQUEST_TIMEOUT).service.getXDSInfo

@app.route('/xds.inp/<int:dcid>')
def get_xds_inp(dcid):
    app.logger.debug('Generating XDS.INP for ID {0}'.format(dcid))
    t0=time.time()

    res = g.getXDSInfo(dcid)
    reqtime = time.time()-t0
    gentime = time.strftime("%a, %d %b %Y %H:%M:%S")
    basedir = request.args.get("basedir", "../links")
    raw_data = request.args.get("basedir") is not None

    metadata = dict()
    res.webservice_request_time = reqtime
    res.timestamp = gentime
    res.raw_data = raw_data

    file_template=res.fileTemplate
    converted = file_template_to_xds(file_template)
    res.fileTemplate = os.path.join(basedir, converted)
    try:
        sr_end = int((res.startImageNumber + res.numberOfImages - 1) / 2)
        sr_start = sr_end - int(3.0/res.dataCollection.axisRange)
        add_sr = [sr_start, sr_end]
        res.additionalSpotRange = "{0} {1}".format(sr_start, sr_end)
    except Exception:
        pass

    template_name = "xds_{0}_{1}.inp".format(res.detectorManufacturer.lower(), res.detectorModel.lower())
    response = make_response(render_template(template_name, data=res))
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/mosflm.inp/<int:dcid>')
def get_mosflm_inp(dcid):
    app.logger.debug('Generating mosflm.inp for ID {0}'.format(dcid))
    t0=time.time()
    res = g.getXDSInfo(dcid)
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
    res = g.getXDSInfo(dcid)
    blname = os.environ.get('BEAMLINENAME')
    if blname is not None:
        templ = 'stac.descr.{0}'.format(blname)
    else:
        templ = 'stac.descr'
    response = make_response(render_template(templ, data=res))
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
    app.run(host='0.0.0.0', port=int(sys.argv[1]), debug=True)
