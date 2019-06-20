#!/usr/bin/env python

import logging
from unittest import TestCase

import requests


class APIError(Exception):
    pass


class APIModel:
    def __init__(self, json_blob, api):
        self.log = logging.getLogger("ConvertKit." + self.__class__.__name__)
        self.api = api
        self.obj = self.decode(json_blob, api)

    def __getattr__(self, attr):
        return self.obj[attr]

    @staticmethod
    def decode(blob, api):
        """A basic decoder that simply returns the blob that is passed in
        """
        return blob

    def __repr__(self):
        return f'<{self.__class__.__name__} {" ".join([f"{k}={v!r}" for k,v in self.obj.items()])}>'

class SubscriptionMixin:
    """A Mixin for object types that support subscriptions/membership

    Requires a class or instance variable MODEL_ENDPOINT
    """

    def list_subscriptions(self, sort_order="asc", subscriber_state=None):
        if not self.api.api_secret:
            raise APIError("Form subscription listing endpoint needs API secret")
        factory = lambda response: [Subscription(x, api=self.api) for x in response['subscriptions']]
        resp = self.api.GET(f'{self.MODEL_ENDPOINT}/{self.id}/subscriptions', factory=factory, api_secret=self.api.api_secret)
        self.log.info(f"{self} subscriptions: {resp}")
        return resp

    def add_subscriber(self, email, first_name=None, params=None, **kwargs):
        params = dict(params) if params else {}
        params.update(kwargs)
        if first_name:
            params["first_name"] = first_name
        resp = self.api.POST(f'{self.MODEL_ENDPOINT}/{self.id}/subscribe',
                             factory=lambda x: Subscription(x['subscription'], api=self.api),
                             email=email, params=params)
        return resp


class Form(APIModel, SubscriptionMixin):
    MODEL_ENDPOINT = "/forms"

    def __str__(self):
        return f"{self.id} {self.name}{' '+self.title if 'title' in self.obj else ''}"

class Subscriber(APIModel):
    pass


class Subscription(APIModel):
    @staticmethod
    def decode(blob, api):
        blob["subscriber"] = Subscriber(blob["subscriber"], api)
        return blob


class Account(APIModel):
    pass

class Course(APIModel, SubscriptionMixin):
    MODEL_ENDPOINT = "/courses"


class Tag(APIModel, SubscriptionMixin):
    MODEL_ENDPOINT = "/tags"




class ConvertKit(object):
    BASE_URL = "https://api.convertkit.com/v3"

    def __init__(self, api_key, api_secret=None, requester=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.requester = requester or requests
        self.log = logging.getLogger(self.__class__.__name__)

    def GET(self, endpoint, factory=None, params=None, **kwargs):
        """Make a GET request to an API endpoint
        """
        params = dict(params) if params is not None else {}
        params["api_key"]=self.api_key
        params.update(kwargs)
        resp = self.requester.get(
            ''.join([self.BASE_URL, endpoint]),
            params=params)
        self.log.debug(f"Response: {resp}  status: {resp.status_code}   json: {resp.json()}")
        if resp.status_code >= 300:
            raise APIError(resp.content)
        if factory:
            return factory(resp.json())
        else:
            return resp.json()

    def POST(self, endpoint, factory=None, params=None, **kwargs):
        """Make a GET request to an API endpoint
        """
        params = dict(params) if params is not None else {}
        params["api_key"]=self.api_key
        params.update(kwargs)
        resp = self.requester.post(
            ''.join([self.BASE_URL, endpoint]),
            data=params)
        self.log.debug(f"Response: {resp}  status: {resp.status_code}")
        if resp.status_code >= 300:
            raise APIError(resp.content)
        # import code; code.interact(banner=f"POST> {endpoint} {params}", local=dict(globals(), **locals()))
        if factory:
            return factory(resp.json())
        else:
            return resp.json()

    def list_forms(self):
        factory = lambda response: [Form(x, api=self) for x in response['forms']]
        resp = self.GET("/forms", factory)
        self.log.info(f"list_forms={resp}")
        return resp

    def find_form(self, form_id=None, form_name=None):
        forms = self.list_forms()
        self.log.info(f'find_form ids = {",".join([str(x.id) for x in forms])}')
        if form_id is not None:
           forms = [f for f in forms if f.id == form_id]
        if form_name is not None:
           forms = [f for f in forms if f.name == form_name]
        if len(forms) == 0:
            raise RuntimeError(f"Did not find a form with matching search form_id={form_id} form_name={form_name}")
        if len(forms) > 1:
            raise RuntimeError(f"More than one form matched search form_id={form_id} form_name={form_name}")
        return forms.pop()

    def account(self):
        if not self.api_secret:
            raise APIError("account endpoint needs API secret")
        resp = self.GET("/account", lambda x: Account(**x), api_secret=self.api_secret)
        self.log.info(f"account={resp}")
        return resp

    def sequences(self):
        factory = lambda response: [Course(x, api=self) for x in response['courses']]
        resp = self.GET("/courses", factory)
        self.log.info(f"sequences={resp}")
        return resp

    def tags(self):
        factory = lambda response: [Tag(x, api=self) for x in response['tags']]
        resp = self.GET("/tags", factory)
        self.log.info(f"tags={resp}")
        return resp

    def create_tag(self, name, description):
        resp = self.POST("/tags", factory=lambda x: Tag(x, api=self), name=name, description=description)
        self.log.info(f"create_tag={resp}")
        return resp


class FormTestCase(TestCase):
    def test_attrs_accessible_like_object(self):
        f = Form(None, None, {'test': 1})
        self.assertEqual(f.test, 1)


if __name__ == '__main__':
    import os, sys
    from pprint import pprint
    import argparse
    import yaml

    cli = argparse.ArgumentParser()
    cli.add_argument("-C", dest="credentials", action="store", default="creds.yaml",
                     type=lambda x: yaml.safe_load(open(x)),
                     help="Credentials config file (default: %(default)s)")
    cli.add_argument("-v", "--verbose", action="store_true", help="Provide verbose informative messages")
    cli.add_argument("-d", "--debug", action="store_true", help=argparse.SUPPRESS)
    cli.add_argument("--form-id", type=int, action="store", help="form identifier to operate against")
    cli.add_argument("--subscriber", nargs=2, metavar="EMAIL FIRST_NAME", action="store",
                     help="subscribe an individual to a form or tag")
    cli.add_argument("command", action="store", help="Command to execute",
                     # really should generate with inspection
                     choices=["list_forms", "account", "sequences", "tags", "list-subscriptions", "subscribe"])
    args = cli.parse_args()

    if args.debug:
        loglevel = logging.DEBUG
    elif args.verbose:
        loglevel = logging.INFO
    else:
        loglevel = logging.WARN
    logging.basicConfig(level=loglevel)
    log = logging.getLogger("ConvertKit.cli")

    key = args.credentials['api_key']
    secret = args.credentials['api_secret']


    ck = ConvertKit(key, api_secret=secret)

    if args.form_id is not None:
        form = ck.find_form(form_id=args.form_id)
        print(form)
        if args.command == "list-subscriptions":
            pprint(form.list_subscriptions())
        if args.command == "subscribe":
            if not args.subscriber:
                log.error("You must specify a subscriber with --subscribe")
                sys.exit(1)
            email, name = args.subscriber
            subscription = form.add_subscriber(email, name)
            print(subscription)
        sys.exit(0)

    method = getattr(ck, args.command)
    if not method:
        log.error(f"Couldn't find execution method for API endpoint {args.command}")
        sys.exit(1)
    results = method()
    try:
        print("\n".join(map(str, results)))
    except TypeError:
        pprint(results)
