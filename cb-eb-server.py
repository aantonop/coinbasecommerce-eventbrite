# Integration between Coinbase Commerce and EventBrite APIs
# (c) Andreas M. Antonopoulos, 2018
# MIT License

# Store configuration in config.json as below
#
# {
# 	"webhook_secret" : "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
# 	"event_id" : "99999999999",
# 	"user_id" : "999999999999",
# 	"eventbrite_token" : "XXXXXXXXXXXXXXXXXXXX"
#	"ticket_price" : 99.9
# }
#

from flask import Flask, request
from coinbase_commerce.webhook import Webhook
from eventbrite import Eventbrite
import logging
import json
from munch import *

# create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# load configuration
config_f = open('config.json', 'r')
config = Munch(json.load(config_f))
config_f.close

app = Flask(__name__)

@app.route('/cbhook', methods=['POST'])
def webhook():
	logger.debug('Received HTTP request')
	if request.method == 'POST':
		logger.debug('HTTP request is type POST')

		# event payload
		request_data = request.data.decode('utf-8')

		# webhook signature
		request_sig = request.headers.get('X-CC-Webhook-Signature', None)

		logger.debug('Validating webhook event signature')
		# signature verification and event object construction
		try:
			event = Webhook.construct_event(request_data, request_sig, config.webhook_secret)
		except (WebhookInvalidPayload, SignatureVerificationError) as e:
			return str(e), 400

		logger.info("Received event: id={id}, code={code}, type={type}".format(id=event.id, code=event.data.code, type=event.type))
		# check event.type. We should only receive charge:confirmed. If webhook is misconfigured we want to ignore pending or failed charges.
		if event.type != "charge:confirmed":
			logger.debug('Event is not a confirmed charge. Waiting...')
			return 'Event received', 200

		logger.debug('Processing confirmed charge')

		# Add all payments and divide by tickets price to get number of tickets purchased
		# event.data.payments is a list, usually contains one payment, but might have more than one.
		try:
			logger.debug('Calculating payment total')
			payment_total = 0

			# add all payments in list
			for payment in event.data.payments:
				payment_total += float(payment.value.local.amount)

			logger.debug('Calculating number of tickets')

			# Payment should be exact multiple of ticket_price
			num_tickets = int(payment_total // config.ticket_price)

			# A confirmed charge should have payment_total > 0
			assert(payment_total > 0)

			# num_tickets should be > 0, if ticket_price is set correctly
			assert(num_tickets > 0)

		except Exception as e:
			logger.error(str(e))
			return 'Error processing event: '+str(e), 400


		logger.debug("Payment total: " + str(payment_total))
		logger.debug("Number of tickets: " + str(num_tickets))

		logger.debug('Creating EventBrite discount code '+str(event.data.code))

		# Create a dicsount code, based on the Coinbase charge code
		# Set quantity to num_tickets and discount to 100%
		eventbrite = Eventbrite(config.eventbrite_token)
		result = eventbrite.post_event_discount(
			config.event_id,
			discount_code=event.data.code,
			discount_percent_off=100,
			discount_quantity_available=num_tickets
		)

		# Check result from EventBrite API
		if 'status_code' in result and result.status_code == 400:
			logger.error("Error creating EventBrite discount code: "+str(result))
			return "Error creating EventBrite discount code", 400
		else:
			logger.info("EventBrite success: "+str(result))
			return 'Success', 200

if __name__ == '__main__':
	app.run()
