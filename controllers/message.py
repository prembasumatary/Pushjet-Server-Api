from flask import Blueprint, jsonify, request
from utils import Error, has_uuid, has_secret, queue_zmq_message, QUERY_ACTION_NEW_MESSAGE
from shared import db, limiter
from models import Listen, Message, Gcm
from datetime import datetime
from config import zeromq_relay_uri, google_api_key
from json import dumps as json_encode

message = Blueprint('message', __name__)


@message.route('/message', methods=['POST'])
@has_secret
def message_send(service):
    text = request.form.get('message')
    if not text:
        return jsonify(Error.ARGUMENT_MISSING('message'))
    level = (request.form.get('level') or '3')[0]
    level = int(level) if level in "12345" else 3
    title = request.form.get('title', '').strip()[:255]
    link = request.form.get('link', '').strip()
    msg = Message(service, text, title, level, link)
    db.session.add(msg)
    db.session.commit()

    if google_api_key:
        Gcm.send_message(msg)

    if zeromq_relay_uri:
        queue_zmq_message(json_encode({"message": msg.as_dict()}))

    service.cleanup()
    db.session.commit()
    return jsonify(Error.NONE)


@message.route('/message', methods=['GET'])
@limiter.limit('15 per minute')
@has_uuid
def message_recv(client):
    listens = Listen.query.filter_by(device=client).all()
    if len(listens) == 0:
        return jsonify({'messages': []})

    msg = []
    for l in listens:
        msg += l.messages().all()
        l.timestamp_checked = datetime.utcnow()

    for l in listens:
        l.service.cleanup()

    ret = jsonify({'messages': [m.as_dict() for m in msg]})
    db.session.commit()
    return ret


@message.route('/message', methods=['DELETE'])
@has_uuid
def message_read(client):
    listens = Listen.query.filter_by(device=client).all()
    if len(listens) > 0:
        for l in listens:
            l.timestamp_checked = datetime.utcnow()

        for l in listens:
            l.service.cleanup()
        db.session.commit()

    return jsonify(Error.NONE)
