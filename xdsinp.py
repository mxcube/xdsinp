#!/usr/bin/env python
import sys
import time
import os.path
from jinja2 import FileSystemLoader
from flask import Flask, render_template, make_response, abort, request
import suds
import re

WSDL_URL='http://pyprocz.esrf.fr:8080/ispyb-ejb3/ispybWS/ToolsForCollectionWebService?wsdl'
#WSDL_URL='http://160.103.210.4:8080/ispyb-ejb3/ispybWS/ToolsForCollectionWebService?wsdl'

app = Flask(__name__)
app.jinja_loader = FileSystemLoader([os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates")])
print os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates")

class IncompleteInformation(Exception):
    pass

@app.route('/xds.inp/<int:dcid>')
def get_xds_inp(dcid):
    t0=time.time()
    c = suds.client.Client(WSDL_URL)
    res = c.service.getXDSInfo(dcid)
    reqtime = time.time()-t0
    gentime = time.strftime("%a, %d %b %Y %H:%M:%S")
    basedir = request.args.get("basedir", "../links")

    try:
        metadata = dict()
        metadata['webservice_request_time'] = reqtime
        metadata['timestamp'] = gentime

        # ispyb has the file template in python's old format string
        # format, XDS only has '?' wildcards. This converts stuff like
        # xqm2-grt36-03w1_1_%04d.img to xqm2-grt36-03w1_1_????.img. We
        # assume there can be only one occurence of the %d format
        # directive. Perhaps there is a more elegant way of doing
        # this.
        file_template=res.dataCollection.fileTemplate
        m = re.match('.+(?P<whole>%(?P<number>[0-9]+)d).*', file_template)
        sanitized = '{before}{wildcard}{after}'.format(before=file_template[0:m.start('whole')],
                                                       wildcard='?'*int(m.group('number')),
                                                       after=file_template[m.end('whole'):])
        res.dataCollection.fileTemplate = os.path.join(basedir, sanitized)
        try:
            sr_end = int((res.dataCollection.startImageNumber + res.dataCollection.numberOfImages - 1) / 2)
            sr_start = sr_end - int(3.0/res.dataCollection.axisRange)
            add_sr = [sr_start, sr_end]
            res.dataCollection.additionalSpotRange = "{0} {1}".format(sr_start, sr_end)
        except Exception:
            pass


    except IncompleteInformation, e:
        return 'Information missing in ISPyB: {0}'.format(e.message), 404
    else:
        template_name = "{0}_{1}.inp".format(res.detector.detectorManufacturer.lower(), res.detector.detectorModel.lower())
        response = make_response(render_template(template_name, metadata=metadata,
                                                 datacollect=res.dataCollection,
                                                 detector=res.detector,
                                                 blsetup=res.beamlineSetup))
        response.headers['Content-Type'] = 'text/plain'
        return response

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(sys.argv[1]), debug=True)
