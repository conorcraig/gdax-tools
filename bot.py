import gdax
import credentials
import accountrecords as records
import accountlogging
import requests
import time
import os
from datetime import datetime
from math import floor

def connectToAPI():

    print("Connecting to API...")
    auth_cl = gdax.AuthenticatedClient(credentials.login['api_key'],
                                    credentials.login['secret'],
                                    credentials.login['passphrase'])
    print("Connected.\n")
    return auth_cl

def stopLoss(auth_cl,orders,product,stopprice,accs):
    
    coin = product.split('-')[0]
    size = float(accs[coin]['balance'])
    size = floor(size*10**8)
    size = size*10**-8
    #determine current stop losses for this product and cancel
    stopLossOrders = []

    if orders:

        for order in orders:

            if orders[order]['product_id'] == product:

                if 'stop' in orders[order]:
                    if orders[order]['stop'] == "loss":
                        stopLossOrders.append(order)

                elif orders[order]['type'] == "stop":
                    if orders[order]['side'] == "sell":
                        stopLossOrders.append(order)

    if size > 0.00000001:
        if stopLossOrders:
            for stopLossOrder in stopLossOrders:
                auth_cl.cancel_order(stopLossOrder)
        else:
            print("no stop losses to cancel for", product)

        r = auth_cl.sell(type="stop",
                    product_id=product,
                    price=stopprice,
                    size=size)
        print(r)

    else:
        print("StopLoss: 0", coin, "balance")

def niceNum(num,dec=2):

    return '{:,}'.format(round(float(num),dec))

def percentageFormat(num,dec=2):

    return '{0:+.2}%'.format(round(float(num)*100,dec))

class myWebSocketClient(gdax.WebsocketClient):

    def listenToWebSocket(self,accs,avgPrice,gains,orders,stopLosses,auth_cl,messageLimit=10):
        
        self.calcAccountValue(accs,products,auth_cl)
        self.get24HrHighs(products,auth_cl) #initialise lastSell values for unrealised gain/loss calcs
        self.start()

        while self.message_count < messageLimit:

            self.calcUnrealisedGains(accs,avgPrice)
            self.printStats(accs,avgPrice,gains,stopLosses)
            
            if self.newHigh:

                newHighDetail = dict.copy(self.newHighDetail)
                self.newHigh = False
                
                stopprice = 0.6*newHighDetail['price']

                stopLoss(auth_cl,
                        orders,
                        product=newHighDetail['product_id'],
                        stopprice=stopprice,
                        accs=accs)

                stopLosses[newHighDetail['product_id']] = stopprice

            if self.orderHeard:
                
                time.sleep(5)
                accs,currencies,tradeHistory,gains,balanceHistory,avgPrice = self.update(auth_cl)
                print(accs)
                print(gains)
                time.sleep(60)
                self.orderHeard = False

            time.sleep(5)

        self.close()

    def on_message(self,msg):
        
        if msg["type"] == "match":

            self.message_count += 1

            if msg['side'] == "sell": #Sell means selling a crypto for EUR as only EUR products are being listened to
                
                #set last sell price
                self.lastSell[msg['product_id']] = float(msg['price'])

                if self.maxValues[msg["product_id"]] < float(msg["price"]):
                    
                    #set new max value
                    self.maxValues[msg["product_id"]] = float(msg["price"])
                    
                    #store detail of new high
                    self.newHighDetail = {'product_id': msg["product_id"],'price': float(msg["price"])}

                    #store message for printing during next cycle of bot
                    newHighMsgList = [msg["product_id"], "\t@ %.2f" % float(msg["price"]), "\t", msg["time"],"\n"]
                    
                    for string in newHighMsgList:
                        self.newHighMsg = self.newHighMsg + str(string)
                    
                    #Enable printing of string in bot and setting of new stop loss
                    self.newHigh = True

                    #first implementation - delete all open orders for chosen product id
                    #final implementation - check if any stop losses are set, delete those (avoids deleting limit orders)
 
            if 'user_id' in msg:
                
                self.orderHeard = True
                #how should this cope when it's responding to orders made by the script itself? 

                #Is it a new order?
                    #if not an activate or recieved type order message, end script/hit restart button
                    #elif limit or stop type, add to orders in memory
                        #update the orders so that it can deal with None being set when it is first called.
                    #elif market type and filled/done
                        #update accounts
                #Is it an existing order?
                    #should only have stored limit/stop types so far unless there was a partially filled 
                    #market order on when getorders was first called.
                    #if stop type
                        #if open type do blah
                        #if partially filled, update accounts
                        #if done type, update accounts and remove from orders 
                    #elif limit type
                        #if open type do blah
                        #if partially filled, update accounts
                        #if done type, update accounts and remove from orders

    def update(auth_cl):
        print("\n")
        print("Updating and saving data...")

        accs = records.getAccounts(auth_cl) 
        fills = records.getFills(auth_cl)

        currencies = records.getCurrencies(accs) 
        tradeHistory = records.compileTradeHistory(fills,accs)
        gains, balanceHistory, avgPrice = records.calcGainsBalancePrice(tradeHistory,currencies)
        accountlogging.logData(gains,avgPrice,balanceHistory,tradeHistory)

        return accs,currencies,tradeHistory,gains,balanceHistory,avgPrice


    def get24HrHighs(self,products,auth_cl):

        # print("24hr highs:")
        for product in products: 
            stats = auth_cl.get_product_24hr_stats(product)
            self.maxValues[product] = float(stats['high'])
            # print(product,stats['high'])

    def calcUnrealisedGains(self,accs,avgPrice):

            self.unrealisedGains = 0.0
            for product in self.lastSell:
                currency = product.split('-')
                currency = currency[0]
                self.unrealisedGains += float(accs[currency]['balance'])*(self.lastSell[product]-avgPrice[currency][-1])

    def calcAccountValue(self,accs,products,auth_cl):

        self.accVal['EUR'] = float(accs['EUR']['balance'])
        self.accBal['EUR'] = float(accs['EUR']['balance'])
        for product in products:
            ticker = auth_cl.get_product_ticker(product)
            self.lastSell[product] = float(ticker['price']) 
            coin = product.split('-')[0]
            # coin = coin[0]
            self.accBal[coin] = float(accs[coin]['balance'])
            self.accVal[coin] = self.accBal[coin] * self.lastSell[product]
            self.accVal['EUR'] += self.accVal[coin]

    def printStats(self,accs,avgPrice,gains,stopLosses):

        os.system("cls")

        print(time.strftime("%c"),"\n")

        print("Balances:")
        print({ 'BTC': niceNum(self.accBal['BTC'],3),
                'ETH': niceNum(self.accBal['ETH'],3),
                'LTC': niceNum(self.accBal['LTC'],3),
                'EUR': niceNum(self.accBal['EUR'])})

        print("Account EUR values:")
        print( {'BTC': niceNum(self.accVal['BTC']),
                'ETH': niceNum(self.accVal['ETH']),
                'LTC': niceNum(self.accVal['LTC'])})
        
        print("Avg Price Paid:")
        print( {'BTC-EUR': niceNum(avgPrice['BTC'][-1]),
                'ETH-EUR': niceNum(avgPrice['ETH'][-1]),
                'LTC-EUR': niceNum(avgPrice['LTC'][-1])})

        print("Lastest sell prices:")
        print( {'BTC-EUR': niceNum(self.lastSell['BTC-EUR']),
                'ETH-EUR': niceNum(self.lastSell['ETH-EUR']),
                'LTC-EUR': niceNum(self.lastSell['LTC-EUR'])})

        print("Highs:")
        print( {'BTC-EUR': niceNum(self.maxValues['BTC-EUR']),
                'ETH-EUR': niceNum(self.maxValues['ETH-EUR']),
                'LTC-EUR': niceNum(self.maxValues['LTC-EUR'])})

        print("Stop Losses:")
        print(stopLosses)
        
        print("Unrealised gains/losses:")
        uGs =  {'BTC-EUR': niceNum(self.accBal['BTC'] * (self.lastSell['BTC-EUR']-float(avgPrice['BTC'][-1]))),
                'ETH-EUR': niceNum(self.accBal['ETH'] * (self.lastSell['ETH-EUR']-float(avgPrice['ETH'][-1]))),
                'LTC-EUR': niceNum(self.accBal['LTC'] * (self.lastSell['LTC-EUR']-float(avgPrice['LTC'][-1])))}
        
        uGsPct = {}
        for product in ['BTC-EUR','ETH-EUR','LTC-EUR']:
            coin = product.split('-')[0] 
            #Avoid zero division error
            if self.accVal[coin] > 0:
                uGsPct[product] = percentageFormat(float(uGs[product])/self.accVal[coin])
            else:
                uGsPct[product] = niceNum(0.0)

        print(uGs)
        print(uGsPct,"\n")

        print(  "Total unrealised gain/loss:\t\t\t", niceNum(self.unrealisedGains),
                "\nRealised gain/loss:\t\t\t\t", niceNum(gains['amount'][-1]),
                "\nCurrent total gain/loss:\t\t\t", niceNum(self.unrealisedGains + gains['amount'][-1]))

        #print("Initial Account Value:\t\t\t\t", niceNum(self.accVal['EUR']))
        print("Current Estimated Account Value*:\t\t", niceNum(self.unrealisedGains + gains['amount'][-1] + 1678.72 + 565.16),
                "\n") #Need to update so it includes future EUR deposits/withdrawls

        print(self.newHighMsg)
        self.newHighMsg = ""
        
        print("Message count:\t",self.message_count,"\n")
        print("------------------------------------------------------------\n")

auth_cl = connectToAPI()

products = ["BTC-EUR", "ETH-EUR", "LTC-EUR"]

wsClient = myWebSocketClient(api_key=credentials.login['api_key'],
                                secret_key=credentials.login['secret'],
                                passphrase=credentials.login['passphrase'],
                                url="wss://ws-feed.gdax.com",
                                products=products,
                                message_type="subscribe")

accs = records.getAccounts(auth_cl) 
fills = records.getFills(auth_cl)
orders = records.getOrders(auth_cl)

currencies = records.getCurrencies(accs) 
tradeHistory = records.compileTradeHistory(fills,accs)
gains, balanceHistory, avgPrice = records.calcGainsBalancePrice(tradeHistory,currencies)

#startup - clear old stop losses as precaution and set new.
#also need to check that price hasn't actually gone below the stopprice already before trying to set
#if successful, will return order dictionary
#if fails, will return dictionary with message key. look for this and cancel script if found... ultimately should figure out how to handle error and try again
#also need to change this to only look at available funds, not balance - in theory, money could be locked up in limit orders, so would be sending too large a sizr
#Needs to find highest price since last buy... means requesting order history since timestamp for latest avgPrice
#check how to set limit for stop loss!

#if trade happens, it will fuck up future trailing stops. need memory to update when trades actually happen (not just recieved)

currentTime = auth_cl.get_time()['iso']

p = '%Y-%m-%dT%H:%M:%S.%fZ'
lastTime = gains['time'][-1]
epoch = datetime(1970, 1, 1)
lastTimeInEpoch = int((datetime.strptime(lastTime, p) - epoch).total_seconds())

#trailing stop loss should be determine by highest price since you entered/reentered a market i.e. from the point in time where you went from 0 balance to >0 balance. 
#Note need to account for really small account balances that are innaccessible... may never get acoount value down to zero.
#maybe you've stayed in the market despite the curent price being lower than what you would theoretically set the limit at. In that case, sell?

# need to decide when to buy back in after a sell!!

stopLosses = {}

for product in products:
    
    coin = product.split('-')[0]

    if float(accs[coin]['balance']) > 0.00000001:

        historicRate = auth_cl.get_product_historic_rates(product,start=lastTime,end=currentTime,granularity=3600)
        i = 0
        t = historicRate[i][0]
    
        while t > lastTimeInEpoch:
            i += 1
            t = historicRate[i][0]

        max = 0.0
    
        for j in range(i):
    
            if historicRate[i][2] > max:
                max = historicRate[i][2] 

        acceptableLoss = 0.4
    
        if max > avgPrice[coin][-1]:
            stopprice = (1.0 - acceptableLoss) * max
        else:
            stopprice = (1.0 - acceptableLoss) * avgPrice[coin][-1]

        stopLoss(auth_cl,
                orders,
                product=product,
                stopprice=stopprice,
                accs=accs)

        stopLosses[product] = stopprice

orders = records.getOrders(auth_cl)

accountlogging.logData(gains,avgPrice,balanceHistory,tradeHistory)

wsClient.listenToWebSocket(accs,avgPrice,gains,orders,stopLosses,auth_cl,messageLimit=500000)

#each time script is restated, clear all stop losses, and set again based on current situation 

#cancel_order(id)
#cancel_all(product)
#get_orders
