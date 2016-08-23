#!/bin/env python3

################################################################
import sys
import pickle

from peewee import *

db = SqliteDatabase('users.db')

class User(Model):
    login = CharField(unique=True, max_length=64)
    password = CharField(unique=True, max_length=64)
    
    class Meta:
        database = db

db.connect()
db.create_tables([User], safe=True)


################################################################
import redis
import tornadoredis
import tornadoredis.pubsub
try:
    pubclient = tornadoredis.Client(host='redis', port=6379)
    pubclient.connect()
except tornadoredis.exceptions.ConnectionError as e:
    print('cannot connect to redis')
    sys.exit()

expire_delay = 1*3600 # 1 hours

################################################################
import tornado.ioloop
import tornado.web
import tornado.websocket

chat_port = '8000'

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user_id = self.get_secure_cookie('user_id')
        if user_id:
            data = pubclient.get('user:' + str(user_id))
            if data:
                return pickle.loads(data)
            try:
                return User.select().where(User.id == int(user_id)).get()
            except:
                return None
        return None

    
class IndexHandler(BaseHandler):
    def get(self):
        self.render('index.html')


class RegisterHandler(tornado.web.RequestHandler):
    def post(self):
        login = self.get_body_argument('login')
        password = self.get_body_argument('password')
        try:
            if not login or not password:
                raise Exception('bad register params')

            # check user
            User.select().where(User.login == login).get()
        except User.DoesNotExist as e:
            user = User.create(login=login, password=password)
            self.redirect('/')
        except Exception as e:
            self.redirect('/')
        else:
            # user already exists
            self.redirect('/')


class LoginHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            login = self.get_body_argument('login')
            password = self.get_body_argument('password')
            if not login or not password:
                raise Exception('bad auth params')
            
            user = User.select().where((User.login == login) & (User.password == password)).get()
            pubclient.setex('user:' + str(user.id), expire_delay, pickle.dumps(user))
            
            self.set_secure_cookie('user_id', str(user.id))
        except User.DoesNotExist as e:
            print(e)
            
        from hashlib import sha1
        import random
        token = sha1((login + str(random.randrange(1000))).encode()).hexdigest()
        self.redirect('/chat/' + token)


class ChatPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, token):
        self.render('chat.html', port=chat_port, token=token)

        
class ChatHandler(BaseHandler, tornado.websocket.WebSocketHandler):

    channel = 'messages'

    def __init__(self, *args, **kvargs):
        super(ChatHandler, self).__init__(*args, **kvargs)
        self.subclient = tornadoredis.Client(host='redis', port=6379)

    @tornado.gen.coroutine
    def listen(self):
        self.subclient.connect()
        yield tornado.gen.Task(self.subclient.subscribe, self.channel)
        self.subclient.listen(self.on_server_message)
        yield tornado.gen.Task(self.subclient.subscribe, '%s.%s'%(self.channel, self.name))
    
    def check_origin(self, origin):
        return True
    
    def open(self, name, token):
        if not token:
            self.close(reason='invalid token')
            return
        self.name = name
        self.listen()
    
    def on_message(self, message):
        if message[0] == '/':
            cmd, _, other = message.partition(' ')
            if cmd == '/pm':
                name, _, msg = other.partition(':')
                newMsg = '_private_ %s -> %s: %s'%(self.name, name, msg)
                pubclient.publish('%s.%s'%(self.channel, name), newMsg)
                self.write_message(newMsg)
        else:
            pubclient.publish(self.channel, '%s: %s'%(self.name, message))
    
    def on_server_message(self, message):
        if message.kind == 'message':
            self.write_message(message.body)
    
    def on_close(self):
        if self.subclient.subscribed:
            self.subclient.unsubscribe(self.channel)
            self.subclient.unsubscribe('%s.%s'%(self.channel, self.name))


################################################################
if __name__ == '__main__':

    settings = {
        'login_url': '/',
        'cookie_secret': '4'
    }
    app = tornado.web.Application([
        (r'/', IndexHandler),
        (r'/register', RegisterHandler),
        (r'/login', LoginHandler),
        (r'/chat/([0-9a-z]+)', ChatPageHandler),
        (r'/wschat/([0-9a-z]+)/([0-9a-z]+)', ChatHandler)
    ], **settings)
    app.listen(8000)
    tornado.ioloop.IOLoop.current().start()
