from flask import request, session, jsonify, render_template, url_for, redirect, flash
import requests
from authlib.integrations.flask_client import OAuth
from functools import wraps
from app import app, db
from app.models import Ticket
import qrcode
import os
from urllib.parse import urlencode

oauth = OAuth(app)
auth0 = oauth.register(
    'auth0',
    client_id=app.config['AUTH0_CLIENT_ID'],
    client_secret=app.config['AUTH0_CLIENT_SECRET'],
    api_base_url=app.config['AUTH0_BASE_URL'],
    access_token_url=f'{app.config["AUTH0_BASE_URL"]}/oauth/token',
    authorize_url=f'{app.config["AUTH0_BASE_URL"]}/authorize',
    client_kwargs={'scope': 'openid profile email'},
)

def get_m2m_token():
    token_url = f"{app.config['AUTH0_BASE_URL']}/oauth/token"
    payload = {
        'client_id': app.config['AUTH0_CLIENT_ID'],
        'client_secret': app.config['AUTH0_CLIENT_SECRET'],
        'audience': app.config['API_AUDIENCE'],
        'grant_type': 'client_credentials'
    }
    headers = {'content-type': 'application/json'}
    response = requests.post(token_url, json=payload, headers=headers)
    if response.status_code == 200:
        return response.json()['access_token']
    else:
        app.logger.error(f'Failed to fetch M2M token: {response.text}')
        return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'profile' not in session:
            session['next'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login')
def login():
    return_to = session.get('next', url_for('index'))
    redirect_uri = url_for('callback', _external=True)
    return auth0.authorize_redirect(redirect_uri=redirect_uri, state=return_to)

@app.route('/logout')
def logout():
    session.clear()
    params = {'returnTo': url_for('index', _external=True), 'client_id': app.config['AUTH0_CLIENT_ID']}
    return redirect(auth0.api_base_url + '/v2/logout?' + urlencode(params))

@app.route('/callback')
def callback():
    try:
        token = auth0.authorize_access_token()
        resp = auth0.get('userinfo')
        userinfo = resp.json()
        session['jwt_payload'] = userinfo
        session['profile'] = {
            'user_id': userinfo['sub'],
            'name': userinfo['name'],
            'picture': userinfo['picture']
        }
        next_page = request.args.get('state') or url_for('index')
        return redirect(next_page)
    except Exception as e:
        flash(f'Login failed: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/')
def index():
    ticket_count = Ticket.query.count()
    return render_template('index.html', ticket_count=ticket_count)

@app.route('/generate-ticket', methods=['POST'])
def generate_ticket():
    m2m_token = get_m2m_token()
    if not m2m_token:
        return jsonify({'error': 'Failed to authenticate with external API'}), 500

    data = request.json
    if Ticket.query.filter_by(vat_id=data['vat_id']).count() >= 3:
        return jsonify({'error': 'Maximum of three tickets allowed per VAT ID'}), 400

    new_ticket = Ticket(vat_id=data['vat_id'], first_name=data['first_name'], last_name=data['last_name'])
    db.session.add(new_ticket)
    db.session.commit()

    qr_directory = os.path.join(app.root_path, 'static', 'qr')
    os.makedirs(qr_directory, exist_ok=True)

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(url_for('ticket_details', ticket_id=str(new_ticket.ticket_id), _external=True))
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img_path = os.path.join(qr_directory, f'{str(new_ticket.ticket_id)}.png')
    img.save(img_path)

    return jsonify({
        'message': 'Ticket generated',
        'ticket_id': str(new_ticket.ticket_id),
        'qr_code': url_for('static', filename='qr/' + str(new_ticket.ticket_id) + '.png', _external=True)
    })

@app.route('/ticket/<ticket_id>')
@login_required
def ticket_details(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template('ticket_details.html', ticket=ticket, ticket_id=str(ticket_id), user=session['profile']['name'])
