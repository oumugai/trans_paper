import locale
locale.setlocale(locale.LC_ALL, 'C')
import tesserocr
from tesserocr import PyTessBaseAPI, RIL, PSM, OEM
from PIL import Image
import cv2
from pdf2image import convert_from_path, convert_from_bytes
import numpy as np
import base64
import requests
import json
import sys
import logging
from flask import Flask, render_template, request
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

app = Flask(__name__)
app.logger.disabled = True  
# werkzeugのLoggerを無効化する
werkzeug_logger = logging.getLogger('werkzeug')   
werkzeug_logger.disabled = True  

@app.route("/res")
def result():
    if request.environ.get('wsgi.websocket'):
        ws = request.environ['wsgi.websocket']
        ws.send(json.dumps({"type":"res", "data":"start"}))
        url=request.args.get('url')
        lang='eng'
        ws.send(json.dumps({"type":"res", "data":"pdf downloading..."}))
        res = requests.get(url)
        ws.send(json.dumps({"type":"res", "data":"converting to image from pdf..."}))
        images = convert_from_bytes(res.content)
        font = cv2.FONT_HERSHEY_SIMPLEX
        ws.send(json.dumps({"type":"res", "data":"create image..."}))
        api =  PyTessBaseAPI(lang=lang, psm=PSM.SINGLE_COLUMN)
        html = ""
        for num, image in enumerate(images):
            ws.send(json.dumps({"type":"progress", "data":"now processing page =>" + str(num+1) + " / " + str(len(images)), "progress":((num+1)/len(images))*100}))
            draw_img = cv2.cvtColor(np.array(image, dtype=np.uint8), cv2.COLOR_RGB2BGR)
            image = image.split()[1]
            image = np.array(image, dtype=np.uint8)
            ret, image = cv2.threshold(image, 254, 255, cv2.THRESH_BINARY)
            copy_img = cv2.cvtColor(np.array(cv2.threshold(image, 60, 255, cv2.THRESH_BINARY)[1], dtype=np.uint8), cv2.COLOR_RGB2BGR)
            for i in range(15):
                image = cv2.GaussianBlur(image,(3,3),0)
                ret, image = cv2.threshold(image, 254, 255, cv2.THRESH_BINARY)
                
            contours, hierarchy = cv2.findContours(image, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            for i in range(len(contours))[::-1]:
                if hierarchy[0][i][3] != -1:
                    epsilon = 0.005*cv2.arcLength(contours[i],True)
                    approx = cv2.approxPolyDP(contours[i],epsilon,True)
                    min_x, min_y = (float("inf")), float("inf")
                    max_x, max_y = (0,0)
                    for pos in approx:
                        if pos[0][0] < min_x:
                            min_x = pos[0][0]
                        if pos[0][1] < min_y:
                            min_y = pos[0][1]
                        if pos[0][0] > max_x:
                            max_x = pos[0][0]
                        if pos[0][1] > max_y:
                            max_y = pos[0][1]
                    appr = np.array([[[min_x, min_y]], [[min_x, max_y]], [[max_x, max_y]],  [[max_x, min_y]]]).reshape((-1,1,2)).astype(np.int32)
                    trim_im = copy_img[min_y:max_y,min_x:max_x]
                    api.SetImage(Image.fromarray(trim_im))
                    box = api.GetComponentImages(RIL.BLOCK, True)
                    try:
                        if api.MeanTextConf() >= 80 and len(api.GetUTF8Text().strip()) > 1:
                            cv2.rectangle(draw_img, (min_x, min_y), (max_x, max_y), (255, 0, 0), 1)
                            tra_res = requests.get("https://script.google.com/macros/s/AKfycbz_S9z9U94pN0UPe4aZJnjFYofy83uYaX6TuBG9nA/exec?text=%s&source=en&target=ja"%(api.GetUTF8Text().strip().replace("\n", " ").replace('"', '\\"')))
                            if tra_res.status_code == 200:
                                string = tra_res.text
                                html += "<p>%s</p><br>"%(string)
                        else:
                            cv2.rectangle(draw_img, (min_x, min_y), (max_x, max_y), (0, 0, 255), 1)
                            img_str = cv2.imencode(".jpg", trim_im)[1].tostring()
                            img_as_text = base64.b64encode(img_str).decode('utf-8')
                            html += "<img src=\"data:image/jpg;base64,%s\" />"%(img_as_text)
                        cv2.putText(draw_img, str(api.MeanTextConf()) + ': ' + str(i) + ': ', (min_x, min_y), font, 0.6, (255,0,255), 1)
                    except:
                        pass
            html += "<br>"

        #with open("result.html", 'w', encoding="utf-8") as file:
        #    file.write(html)
        ws.send(json.dumps({"type":"res", "data":"done"}))
        ws.send(json.dumps({"type":"html", "data":html}))
    
@app.route("/trans")
def trans():
    return render_template('trans.html', url=request.args.get('url'))

@app.route("/")
def index():
    return render_template('index.html')

@app.route('/pipe')
def pipe():
    if request.environ.get('wsgi.websocket'):
        ws = request.environ['wsgi.websocket']
        while True:
            ws.send(input())

if __name__ == '__main__':
    app.debug = True
    server = pywsgi.WSGIServer(("", 8000), app, handler_class=WebSocketHandler, log=logging.getLogger('pyswgi'), error_log=logging.getLogger('pyswgi'))
    server.serve_forever()