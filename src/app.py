from flask import Flask, jsonify, request, url_for, redirect
from db import db
from flask_cors import CORS
from flask_migrate import Migrate
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
# from dotenv import load_dotenv
from flask_mail import Mail, Message
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager
from werkzeug.security import generate_password_hash, check_password_hash
import os

from models.notes import Note
from models.calendar import Fecha
from models.profile import Profile
from models.user import User
from datetime import timedelta


# app config
app = Flask(__name__)
app.url_map.slashes = False

app.config["DEBUG"] = True
uri = os.getenv("DATABASE_URL", "sqlite:///database.db")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv('JWT_SECRET_KEY')
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False
app.config["ENV"] = 'development'


# app.config.from_object('default_config')


MIGRATE = Migrate(app, db)
jwt = JWTManager(app)
db.init_app(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['JWT_SECRET_KEY'])

CORS(app)


@app.before_first_request
def create_tables():
    db.create_all()


@app.route('/')
def get_home():
    return "<h1>Serenity REST API</h1>"


@app.route('/api/auth', methods=['POST'])
def login():
    nombre_usuario = request.json.get('nombre_usuario', None)
    password = request.json.get('password', None)
    user = User.query.filter_by(nombre_usuario=nombre_usuario).first()

    if user and check_password_hash(user.password, password):
        if user.confirmed_email:
            token = create_access_token(
                identity=user.id,
                expires_delta=timedelta(weeks=1)
            )
            return jsonify(access_token=token)
        else:
            return jsonify(message='email not verified, please check your mail inbox to validate it'), 403

    else:
        return jsonify(message="Bad username or password."), 400


@app.route('/api/register', methods=['POST'])
def register():
    nombre_usuario = request.json.get('nombre_usuario', None)
    password = request.json.get('password', None)
    email = request.json.get('email', None)
    user_img = request.json.get('user_img', "")

    user = User.query.filter_by(nombre_usuario=nombre_usuario).first()

    if user:
        return jsonify(message=f"El usuario '{nombre_usuario}' ya existe.", status="error"), 400

    user = User.query.filter_by(email=email).first()

    if user:
        return jsonify(message=f"E-mail '{email}' ya está en uso.", status="error"), 400

    if nombre_usuario is None or password is None or email is None:
        return jsonify(message="Debes incluir un nombre de usuario, email y contraeña.", status="error"), 400

    if nombre_usuario == "" or password == "" or email == "":
        return jsonify(message="Debes incluir un nombre de usuario, email y contraeña.", status="error"), 400

    newProfile = Profile()
    newProfile.avatar = user_img
    user = User(
        nombre_usuario=nombre_usuario,
        password=generate_password_hash(password),
        email=email,
        perfil=newProfile)

    user.save()
    emailToken = serializer.dumps(user.id, salt=app.config['JWT_SECRET_KEY'])
    msg = Message(
        'Confirm Email',
        sender=app.config['MAIL_USERNAME'], recipients=[email])
    link = url_for('confirm_email', token=emailToken, _external=True)

    msg.body = f'Confirm email account link: {link}'

    mail.send(msg)

    return jsonify(
        user=user.serialize(),
        status="ok"
    )


@app.route('/confirm_email/<token>')
def confirm_email(token):
    try:
        user_id = serializer.loads(
            token, salt=app.config['JWT_SECRET_KEY'], max_age=300)
    except SignatureExpired:
        return jsonify(message="The token is expired.")

    user = User.query.get(user_id)
    if user:
        user.confirmed_email = True
        user.save()
        # headers = {
        #     "Content-Type": "text/html"
        # }
        return redirect(f"{os.getenv('CLIENT_FRONT_URL')}/confirm-email/{user.email}", code=302)
        # return make_response(render_template("confirm_page.html", email=user.email), 200, headers)
    else:
        return jsonify(message="User not found"), 400


@app.route('/api/users')
def get_users():
    return jsonify(users=[user.serialize() for user in User.query.all()])


@app.route('/api/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    nombre = request.json.get('nombre')
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    user.perfil.nombre = nombre
    user.save()

    return jsonify(user.serialize())


@app.route('/api/profile')
@jwt_required()
def get_profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    return jsonify(user.serialize())


@app.route('/api/note', methods=['POST'])
@jwt_required()
def create_note():
    nota = Note()
    nota.titulo = request.json.get('titulo')
    nota.contenido = request.json.get('contenido')
    nota.categoria = request.json.get('categoria')

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    nota.perfil = user.perfil
    nota.save()

    return jsonify(nota.serialize())


@app.route('/api/calendar', methods=['POST'])
@jwt_required()
def save_calendar():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    user.perfil.calendario = []
    for fecha, category in request.get_json().items():
        newFecha = Fecha(fecha=fecha, category=category)
        user.perfil.calendario.append(newFecha)
    user.save()

    return jsonify(message="added_calendar")


@app.route('/api/tokencheck', methods=['POST'])
@jwt_required()
def check_token():
    user_id = get_jwt_identity()
    token = create_access_token(
        identity=user_id,
        expires_delta=timedelta(weeks=1)
    )
    return jsonify(access_token=token)


@app.route('/api/note/<int:_id>', methods=['DELETE'])
@jwt_required()
def delete_note(_id):
    note = Note.query.get(_id)
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    user.perfil.notas.remove(note)
    user.save()

    return jsonify(user.serialize())

# @app.route('/api/test')
# @jwt_required()
# def test():
#     user_id = get_jwt_identity()
#     user = User.query.get(user_id)
#     if user.confirmed_email:
#         return jsonify(user.serialize())
#     else:
#         return jsonify(message='Usuario sin confimar email')


@app.route('/api/reset-password', methods=['POST'])
def resetPassword():
    emailToken = request.json.get('emailToken')
    password = request.json.get('password')

    email = serializer.loads(
        emailToken, salt=app.config['JWT_SECRET_KEY'], max_age=300)

    user = User.query.filter_by(email=email).first()
    if user:
        user.password = generate_password_hash(password)
        user.save()
        return jsonify(message='succed changing password'), 200
    return jsonify(message='User does not exists with that email'), 400


@app.route('/api/reset-by-mail', methods=['POST'])
def sendMailReset():
    email = request.json.get('email')
    emailToken = serializer.dumps(email, salt=app.config['JWT_SECRET_KEY'])
    msg = Message(
        'Reset password',
        sender=app.config['MAIL_USERNAME'], recipients=[email])
    linkFront = f'{os.getenv("CLIENT_FRONT_URL")}/forgot-password/{emailToken}'
    # link = url_for('reset-password', token=emailToken, _external=True)

    msg.body = f'Reiniciar contraseña url: {linkFront}'

    mail.send(msg)

    return jsonify(message='email sended')


if __name__ == '__main__':
    app.run()
