def trlngStpLss()
## Bot for setting trailing stop loss in GDAX

#Connect to API


#determine current accounts

products = []

#Monitoring loop
accLossPct = 0.15 #percentage to trail price by
while True
	if accLossPct*mktPr > stpLss:
		stpLss	= accLossPct*mktPr
		#remove old stop loss
		#push new stop loss to GDAX
		#pause before checking again

#include error checking

