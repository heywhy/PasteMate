from flask import after_this_request, request
from flask_restful import Resource
from flask_jwt_extended import (create_access_token, create_refresh_token, jwt_required,
                                jwt_refresh_token_required, get_jwt_identity, get_raw_jwt,
                                set_access_cookies, set_refresh_cookies, unset_jwt_cookies)
from api.forms import RegistrationForm, LoginForm, SubmitPasteForm
from db.models import Account, Paste, RevokedToken
from datetime import timedelta


def create_tokens(user):
    access_expiration = timedelta(days=7)
    refresh_expiration = timedelta(days=14)
    access_token = create_access_token(identity=user.username, fresh=True, expires_delta=access_expiration)
    refresh_token = create_refresh_token(identity=user.username, expires_delta=refresh_expiration)
    return [access_token, refresh_token]


def set_cookies(tokens, response):
    set_access_cookies(response, tokens[0])
    set_refresh_cookies(response, tokens[1])


class RegisterUser(Resource):
    def post(self):
        data = request.get_json(force=True)
        form = RegistrationForm.from_json(data)
        if not form.validate():
            return {'errors': form.errors}, 400
        user = Account(**data)
        user.save_to_db()

        @after_this_request
        def set_jwt_cookies(response):
            user_tokens = create_tokens(user)
            set_cookies(user_tokens, response)
            return response

        return {'username': user.username, 'userID': user.id, 'email': user.email}, 201


class LoginUser(Resource):
    def post(self):
        data = request.get_json(force=True)
        form = LoginForm.from_json(data)
        if not form.validate():
            return {'errors': form.errors}, 401
        user = Account.find_by_username(data.get('username'))

        @after_this_request
        def set_jwt_cookies(response):
            user_tokens = create_tokens(user)
            set_cookies(user_tokens, response)
            return response

        return {'username': user.username, 'userID': user.id, 'email': user.email}, 200


class SubmitPaste(Resource):
    @jwt_required
    def post(self):
        data = request.get_json(force=True)
        form = SubmitPasteForm.from_json(data)
        if not form.validate():
            return {'errors': form.errors}, 401
        identity = get_jwt_identity()
        data['owner_id'] = Account.find_by_username(identity).id
        this_paste = Paste(**data)
        this_paste.save_to_db()
        return {'paste_uuid': this_paste.paste_uuid}, 200


class ViewPaste(Resource):
    def get(self, paste_uuid):
        paste = Paste.find_by_uuid(paste_uuid)
        if paste is None:
            return {'error': 'Paste with requested UUID was not found.'}, 404
        if paste.password is not None:
            return {'error': 'password is required'}, 401
        return {'paste': paste.paste_dict()}, 200

    def post(self, paste_uuid):
        data = request.get_json(force=True)
        if 'password' in data:
            paste = Paste.find_by_uuid(paste_uuid)
            if paste.password_correct(data['password']):
                return {'paste': paste.paste_dict()}, 200
            return {'error': 'password is incorrect.'}, 401
        return {'error': 'Password required.'}, 401


class EditPaste(Resource):
    @jwt_required
    def get(self, paste_uuid):
        paste = Paste.find_by_uuid(paste_uuid)
        if paste is None:
            return {'error': 'Paste not found'}, 404
        identity = get_jwt_identity()
        current_user_id = Account.find_by_username(identity).id
        if paste.owner_id != current_user_id and not paste.open_edit:
            return {'error': 'You are not the owner of this paste, and open edit is not enabled for it.'}, 401
        paste_information = paste.paste_dict()
        # Strip out unneeded information and set expiration to 0 for client
        for key in ['deletion_inbound', 'expiration_date']:
            paste_information.pop(key)
        paste_information['expiration'] = 0
        return {'paste': paste_information}, 200

    @jwt_required
    def post(self, paste_uuid):  # Just in case someone tries to get dirty with post requests, verify things here too.
        paste = Paste.find_by_uuid(paste_uuid)
        if paste is None:
            return {'error': 'Paste not found'}, 404
        data = request.get_json(force=True)
        form = SubmitPasteForm.from_json(data)
        if not form.validate():
            return {'errors': form.errors}, 401
        identity = get_jwt_identity()
        current_user_id = Account.find_by_username(identity).id
        if paste.owner_id != current_user_id and not paste.open_edit:
            return {'error': 'You are not the owner of this paste, and open edit is not enabled for it.'}, 401
        if paste.owner_id != current_user_id and paste.open_edit:
            # Restrict changes to the password, expiration date, and open edit settings if they are not
            # the paste owner.
            data['password'] = None
            data['open_edit'] = None
            data['expiration'] = None
        paste.update_paste(**data)
        return {'paste_uuid': paste.paste_uuid}, 200


class DeletePaste(Resource):
    @jwt_required
    def get(self, paste_uuid):
        paste = Paste.find_by_uuid(paste_uuid)
        identity = get_jwt_identity()
        current_user_id = Account.find_by_username(identity).id
        if paste is None:
            return {'error': 'Paste not found'}, 404
        if paste.owner_id != current_user_id:
            return {'error': 'You can not delete pastes you do not own.'}, 401
        paste.delete()
        return {'result': 'Paste deleted.'}, 204


class ListPastes(Resource):
    @jwt_required
    def get(self, page):
        def strf_date(date): return date.strftime("%Y-%m-%d %H:%M:%S") if date is not None else None
        identity = get_jwt_identity()
        current_user = Account.find_by_username(identity)
        paste_pagination = current_user.pastes.paginate(int(page), 10, False)
        pastes = []
        for paste in paste_pagination.items:
            pastes.append({
                'uuid': paste.paste_uuid,
                'title': paste.title,
                'language': paste.language,
                'submission_date': strf_date(paste.submission_date),
                'expiration_date': strf_date(paste.expiration_date),
                'edit_date': strf_date(paste.edit_date),
                'open_edit': paste.open_edit,
                'password_protected': paste.password is not None
            })
        return {'pastes': {
            'current_page': paste_pagination.page,
            'last_page': paste_pagination.pages,
            'next_page_url': ('/api/paste/list/%i' % paste_pagination.next_num) if paste_pagination.has_next else None,
            'prev_page_url': ('/api/paste/list/%i' % paste_pagination.prev_num) if paste_pagination.has_prev else None,
            'data': pastes
        }}


class RevokeAccess(Resource):
    @jwt_required
    def get(self):
        @after_this_request
        def revoke_access(response):
            jti = get_raw_jwt()
            revoked_token = RevokedToken(jti=jti['jti'])
            revoked_token.save_to_db()
            unset_jwt_cookies(response)
            return response
        return {'token_revoked': True}, 200


class RefreshUser(Resource):
    @jwt_refresh_token_required
    def post(self):
        current_username = get_jwt_identity()
        access_token = create_access_token(identity=current_username)
        response = {'token_refreshed': True}
        set_access_cookies(response, access_token)
        return response, 200


class CurrentUser(Resource):
    @jwt_required
    def get(self):
        current_username = get_jwt_identity()
        user = Account.find_by_username(current_username)
        return {'username': current_username, 'userID': user.id, 'email': user.email}
        # Nothing else needed since the loader should do the rest.
