from datetime import datetime, timedelta

from flask import (
        Blueprint, render_template, request, url_for,
        redirect, g)
from flask_security import logout_user as logout
from sqlalchemy import desc, func

from mhn.ui.utils import get_flag_ip, get_sensor_name
from mhn.api.models import (
        Sensor, Rule, DeployScript as Script,
        RuleSource)
from mhn.auth import login_required, current_user
from mhn.auth.models import User, PasswdReset, ApiKey
from mhn import db, mhn
from mhn.common.utils import (
        paginate_options, alchemy_pages, mongo_pages)
from mhn.common.clio import Clio

ui = Blueprint('ui', __name__, url_prefix='/ui')
from mhn import mhn as app

@app.template_filter()
def number_format(value):
    return '{:,d}'.format(value)

@ui.before_request
def check_page():
    """
    Cleans up any query parameter that is used
    to build pagination.
    """
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    g.page = page


@ui.route('/login/', methods=['GET'])
def login_user():
    if current_user.is_authenticated():
        return redirect(url_for('ui.dashboard'))
    return render_template('security/login_user.html')


@mhn.route('/')
@ui.route('/dashboard/', methods=['GET'])
@login_required
def dashboard():
    clio = Clio()
    # Number of attacks in the last 24 hours.
    attackcount = clio.session.count(hours_ago=24)
    # TOP 5 attacker ips.
    top_attackers = clio.session.top_attackers(top=5, hours_ago=24)
    # TOP 5 attacked ports
    top_ports = clio.session.top_targeted_ports(top=5, hours_ago=24)
    # TOP 5 sigs
    freq_sigs = clio.hpfeed.top_sigs(top=5, hours_ago=24)

    return render_template('ui/dashboard.html',
                           attackcount=attackcount,
                           top_attackers=top_attackers,
                           top_ports=top_ports,
                           freq_sigs=freq_sigs,
                           get_flag_ip=get_flag_ip)


@ui.route('/attacks/', methods=['GET'])
@login_required
def get_attacks():
    clio = Clio()
    options = paginate_options(limit=10)
    options['order_by'] = '-timestamp'
    total = clio.session.count(**request.args.to_dict())
    sessions = clio.session.get(
            options=options, **request.args.to_dict())
    sessions = mongo_pages(sessions, total, limit=10)
    return render_template('ui/attacks.html', attacks=sessions,
                           sensors=Sensor.query, view='ui.get_attacks',
                           get_flag_ip=get_flag_ip, get_sensor_name=get_sensor_name,
                           **request.args.to_dict())

@ui.route('/feeds/', methods=['GET'])
@login_required
def get_feeds():
    clio = Clio()
    options = paginate_options(limit=10)
    options['order_by'] = '-_id'
    count,columns,feeds = clio.hpfeed.get_payloads(options, request.args.to_dict())
    channel_list = clio.hpfeed.channel_map.keys()
    feeds = mongo_pages(feeds, count, limit=10)
    return render_template('ui/feeds.html', feeds=feeds, columns=columns,
                           channel_list=channel_list, view='ui.get_feeds',
                           **request.args.to_dict())

@ui.route('/rules/', methods=['GET'])
@login_required
def get_rules():
    if 'sig_name' in request.args:
        search = '%%%s%%' % request.args.get('sig_name')
        rules = db.session.query(Rule, func.count(Rule.rev).label('nrevs')).\
            filter(Rule.message.like(search)).\
            group_by(Rule.sid).\
            order_by(desc(Rule.date))
    else:
        rules = db.session.query(Rule, func.count(Rule.rev).label('nrevs')).\
            group_by(Rule.sid).\
            order_by(desc(Rule.date))
    rules = alchemy_pages(rules, limit=10)
    return render_template('ui/rules.html', rules=rules, view='ui.get_rules', **request.args.to_dict())


@ui.route('/rule-sources/', methods=['GET'])
@login_required
def rule_sources_mgmt():
    sources = RuleSource.query
    return render_template('ui/rule_sources_mgmt.html', sources=sources)


@ui.route('/sensors/', methods=['GET'])
@login_required
def get_sensors():
    sensors = Sensor.query.all()
    total = Sensor.query.count()
    # Paginating the list.
    pag = paginate_options(limit=10)
    sensors = sensors[pag['skip']:pag['skip'] + pag['limit']]
    # Using mongo_pages because it expects paginated iterables.
    sensors = mongo_pages(sensors, total, limit=10)
    return render_template('ui/sensors.html', sensors=sensors,
                           view='ui.get_sensors', pag=pag)


@ui.route('/add-sensor/', methods=['GET'])
@login_required
def add_sensor():
    return render_template('ui/add-sensor.html')


@ui.route('/manage-deploy/', methods=['GET'])
@login_required
def deploy_mgmt():
    script_id = request.args.get('script_id')
    if not script_id or script_id == '0':
        script = Script(name='', notes='', script='')
    else:
        script = Script.query.get(script_id)
    return render_template(
            'ui/script.html', scripts=Script.query.order_by(Script.date.desc()),
            script=script)

@ui.route('/honeymap/', methods=['GET'])
@login_required
def honeymap():
    return render_template('ui/honeymap.html')

@ui.route('/add-user/', methods=['GET'])
@login_required
def settings():
    return render_template(
        'ui/settings.html', 
        users=User.query.filter_by(active=True),
        apikey=ApiKey.query.filter_by(user_id=current_user.id).first()
    )


@ui.route('/forgot-password/<hashstr>/', methods=['GET'])
def forgot_passwd(hashstr):
    logout()
    user = PasswdReset.query.filter_by(hashstr=hashstr).first().user
    return render_template('ui/reset-password.html', reset_user=user,
                           hashstr=hashstr)


@ui.route('/reset-password/', methods=['GET'])
def reset_passwd():
    return render_template('ui/reset-request.html')
