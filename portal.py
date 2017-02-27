#!/usr/bin/env python3

import os
import datetime
import argparse
# import logging

from flask import (
    Flask,
    render_template,
    url_for,
    redirect,
    send_from_directory,
    session,
    request,
    abort,
    json,
)
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from flask_sqlalchemy import SQLAlchemy, _QueryProperty

import model as m
# Default ordering for admin types
m.Semesters.order_by = m.Semesters.title
m.Professors.order_by = m.Professors.last_first
m.Courses.order_by = m.Courses.number
m.Sections.order_by = m.Sections.number
m.ProblemTypes.order_by = m.ProblemTypes.description

# Create App
app = Flask(__name__)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Attach Database
db = SQLAlchemy(app)
db.Model = m.Base
# Ugly code to make Base.query work
m.Base.query_class = db.Query
m.Base.query = _QueryProperty(db)


def create_app(args):
    r"""
    Sets up app for use
    Adds logging, database configuration, and the secret key
    """
    global app, db
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    # setup Logging
    # log = logging.getLogger('FlaskApp')
    # log.setLevel(logging.ERROR)
    # app.logger.addHandler(log)

    # setup Database
    app.config['SQLALCHEMY_DATABASE_URI'] = '{}:///{}'.format(
        args.type, args.database)
    db.create_all()

    # setup config values
    with app.app_context():
        config = {
            'SECRET_KEY': os.urandom(24),
            'PERMANENT_SESSION_LIFETIME': '30',
        }
        # get Config values from database
        for name in config:
            try:
                key = m.Config.query.filter_by(name=name).one()
                config[name] = key.value
            except NoResultFound:
                key = m.Config(name=name, value=config[name])
                db.session.add(key)
                db.session.commit()

        config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(
            minutes=int(config['PERMANENT_SESSION_LIFETIME']))
        app.config.update(config)


def date(string):
    r"""
    Convert a date formated string to a date object
    """
    return datetime.datetime.strptime(string, '%Y-%m-%d').date()


def get_int(string):
    r"""
    Convert a string to int returning none for invalid strings
    """
    ret = None
    if string is not None:
        try:
            ret = int(string)
        except ValueError:
            pass
    return ret


@app.context_processor
def context():
    return dict(m=m)


def error(e, message):
    r"""
    Basic error template for all error pages
    """
    user = get_user()
    html = render_template(
        'error.html',
        title=str(e),
        message=message,
        user=user,
    )
    return html


@app.errorhandler(403)
def four_oh_three(e):
    r"""
    403 (forbidden) error page
    """
    return error(
        e,
        "You don't have access to this page."
    ), 403


@app.errorhandler(404)
def four_oh_four(e):
    r"""
    404 (page not found) error page
    """
    return error(
        e,
        "We couldn't find the page you were looking for."
    ), 404


@app.errorhandler(500)
def five_hundred(e):
    r"""
    500 (internal server) error page
    Will have to be changed for production version
    """
    if isinstance(e, NoResultFound):
        message = 'Could not find the requested item in the database.'
    elif isinstance(e, MultipleResultsFound):
        message = 'Found too many results for the requested resource.'
    else:
        message = 'Whoops, looks like something went wrong!'
    return error(
        '500: '+str(e),
        message,
    ), 500


def get_user():
    r"""
    Gets the user data from the current session
    Returns the Tutor object of the current user
    """
    id = session.get('username')
    user = None
    if id:
        if app.config['DEBUG']:
            user = m.Tutors(email=id, is_active=True, is_superuser=True)
        else:
            try:
                user = m.Tutors.query.filter_by(email=id).one()
            except NoResultFound:
                session.clear()

        if user and not user.is_active:
            session.clear()
            user = None
    return user


@app.route('/favicon.ico')
def favicon():
    r"""
    The favorites icon for the site
    """
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'images'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon',
    )


@app.route('/index.html')
@app.route('/')
def index():
    r"""
    The home page, from which tutors can login and students can open tickets
    """
    user = get_user()
    html = render_template(
        'index.html',
        home=True,
        user=user,
    )
    return html


@app.route('/status.html')
def status():
    r"""
    A status page for the CSLC

    For students displays:
        Annoucements
        Course Availability

    For tutors, also displays:
        Open Tickets
    """
    user = get_user()
    html = render_template(
        'status.html',
        user=user,
    )
    return html


@app.route('/open_ticket/index.html')
@app.route('/open_ticket/')
def open_ticket():
    r"""
    The student page for opening a ticket
    """
    user = get_user()
    html = render_template(
        'open_ticket.html',
        user=user,
    )
    return redirect(url_for('index'))


@app.route('/close_ticket/<ticket>')
def close_ticket(ticket):
    r"""
    The tutor page for claiming and closing tickets
    """
    user = get_user()
    if not user:
        return abort(403)

    html = render_template(
        'close_ticket.html',
        user=user,
    )
    return redirect(url_for('index'))


# ----#-   Administration tools
@app.route('/admin/index.html')
@app.route('/admin/')
def admin():
    r"""
    The admin configutration page
    Can add professors, semesters, courses, sections, tutors, and more
    """
    user = get_user()
    if not user or not user.is_superuser:
        return abort(403)

    html = render_template(
        'admin.html',
        user=user,
    )
    return html


def edit_object(obj, values, id):
    r"""
    Basic object diff handler for editing most ORM objects
    """
    if id:
        obj = obj.query.filter_by(id=id).one()
        for key, value in values.items():
            if getattr(obj, key) != value:
                setattr(obj, key, value)
    else:
        s = obj(**values)
        db.session.add(s)
    db.session.commit()
    return obj


@app.route('/admin/semesters/index.html')
@app.route('/admin/semesters/')
def semesters():
    r"""
    Displays and allows editing of the available semesters
    """
    user = get_user()
    if not user or not user.is_superuser:
        return abort(403)

    html = render_template(
        'semesters.html',
        user=user,
        semesters=m.Semesters.query.all(),
    )
    return html


@app.route('/admin/semesters/new')
@app.route('/admin/semesters/<int:id>')
def edit_semester(id=None):
    r"""
    Allows editing of an existing semester and creation of new ones
    """
    user = get_user()
    if not user or not user.is_superuser:
        return abort(403)

    if id is None:
        semester = None
    else:
        semester = m.Semesters.query.filter_by(id=id).one()

    html = render_template(
        'edit_semester.html',
        user=user,
        obj=semester,
        type=m.Semesters,
    )
    return html


@app.route('/admin/semesters/', methods=['POST'])
def edited_semesters():
    r"""
    Handles changes to semester objects
    """
    if request.form.get('action') == 'delete':
        m.Semesters.query.filter_by(id=request.form.get('id')).delete()
        db.session.commit()
    else:
        form = {
            'year': int(request.form['year']),
            'season': m.Seasons(int(request.form['season'])),
            'start_date': datetime.datetime.strptime(
                request.form['start_date'],
                '%Y-%m-%d',
            ).date(),
            'end_date': datetime.datetime.strptime(
                request.form['end_date'],
                '%Y-%m-%d',
            ).date(),
        }
        edit_object(m.Semesters, form, request.form.get('id'))
    return redirect(url_for('semesters'))


@app.route('/admin/professors/index.html')
@app.route('/admin/professors/')
def professors():
    r"""
    Displays and allows editing of the available professors
    """
    user = get_user()
    if not user or not user.is_superuser:
        return abort(403)

    html = redirect(url_for('admin'))
    return html


@app.route('/admin/courses/index.html')
@app.route('/admin/courses/')
def courses():
    r"""
    Displays and allows editing of the available courses
    """
    user = get_user()
    if not user or not user.is_superuser:
        return abort(403)

    html = redirect(url_for('admin'))
    return html


@app.route('/admin/sections/index.html')
@app.route('/admin/sections/')
def sections():
    r"""
    Displays and allows editing of the available course sections
    """
    user = get_user()
    if not user or not user.is_superuser:
        return abort(403)

    html = redirect(url_for('admin'))
    return html


@app.route('/admin/tutors/index.html')
@app.route('/admin/tutors/')
def tutors():
    r"""
    Displays and allows editing of the tutors
    """
    user = get_user()
    if not user or not user.is_superuser:
        return abort(403)

    html = redirect(url_for('admin'))
    return html


# ----#-   Login/Logout
@app.route('/login/')
def login():
    r"""
    Redirects the user to the UNO Single Sign On page
    """
    session.clear()
    if app.config['DEBUG']:
        session['username'] = 'test@unomaha.edu'
        html = redirect(url_for('index'))
    else:
        html = redirect('https://auth.unomaha.edu/idp/Authn/UserPassword')
    return html


@app.route('/logout/')
def logout():
    r"""
    Logs the user out and returns them to the homepage
    """
    session.clear()
    html = redirect(url_for('index'))
    return html


# ----#-   JSON
@app.route('/tickets.json')
def json_status():
    r"""
    Query needs checking
    """
    user = get_user()
    if not user:
        return abort(403)

    data = m.Tickets.query.filter(
        m.Tickets.status.in_((None, m.Status.Open))
    ).all()
    data = list(map(lambda a: a.dict(), data))
    return json.jsonify(d=data)


@app.route('/availability.json')
def json_availability():
    r"""
    Query needs checking
    Output needs checking
    """
    today = datetime.date.today()
    data = m.Courses.query.\
        join(m.can_tutor_table).join(m.Tutors).\
        join(m.Sections).join(m.Tickets).join(m.Semesters).\
        filter(m.Courses.on_display is True).\
        filter(m.Tickets.in_((None, m.Status.Open, m.Status.Claimed))).\
        filter(m.Semesters.start_date <= today).\
        filter(m.Semesters.end_date >= today).\
        all()
    lst = []
    for course in data:
        tickets = sum(len(section.tickets) for section in course.sections)
        tutors = len(course.tutors)
        lst.append({'course': course, 'tickets': tickets, 'tutors': tutors})
    return json.jsonify(d=data)


def main():
    port = 80  # default port
    parser = argparse.ArgumentParser(
        description='Tutoring Portal Server',
        epilog='The server runs locally on port %d if PORT is not specified.'
        % port)
    parser.add_argument(
        '-p, --port', dest='port', type=int,
        help='The port where the server will run')
    parser.add_argument(
        '-d, --database', dest='database', default=':memory:',
        help='The database to be accessed')
    parser.add_argument(
        '-t, --type', dest='type', default='sqlite',
        help='The type of database engine to be used')
    parser.add_argument(
        '--debug', dest='debug', action='store_true',
        help='run the server in debug mode')
    parser.add_argument(
        '--reload', dest='reload', action='store_true',
        help='reload on source update without restarting server (also debug)')
    args = parser.parse_args()
    if args.reload:
        args.debug = True

    if args.port is None:  # Private System
        args.port = port
        host = '127.0.0.1'
    else:  # Public System
        host = '0.0.0.0'

    create_app(args)

    app.run(
        host=host,
        port=args.port,
        debug=args.debug,
        use_reloader=args.reload,
    )

if __name__ == '__main__':
    main()
