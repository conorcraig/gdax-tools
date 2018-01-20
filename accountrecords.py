import sys

def unpaginate(PagData,sortBy=None):
    data = []
    for PageNum in range(0,len(PagData)):
        data.extend(PagData[PageNum])
    if sortBy is not None:
        data = sorted(data, key=lambda k: k[sortBy])
    return(data)

def getCurrencies(accs):
    currencies = []
    for acc in accs:
        currencies.append(acc)
    return(currencies)

def getFills(auth_cl):
    fillsPaginated = auth_cl.get_fills()
    fills = unpaginate(fillsPaginated,sortBy='created_at')
    return(fills)

def getAccounts(auth_cl):
    print("Get all currency accounts.")
    accsList = auth_cl.get_accounts() #Pull details of each currency account
    accs = {} 
    #For each account, get current balance and pull transfer history.
    for acc in accsList:
        print(acc['currency'], acc['balance'])
        # print('Getting account history...')
        historyPaginated = auth_cl.get_account_history(acc['id'])
        history = unpaginate(historyPaginated,sortBy='created_at')
        #Extract only transfers from account history
        # print('Extracting transfer history...')
        transferHistory = [d for d in history if d['type'] in ['transfer']]
        acc['history'] = transferHistory
        # print("Transfer history extracted.\n")
        #Create dictionary each currency for easier access
        accs[acc['currency']] = acc
    return(accs)

def getOrders(auth_cl):
    ordersPaginated = auth_cl.get_orders()
    orders = unpaginate(ordersPaginated)
    orderdict = {}
    for order in orders:
        orderdict[order['id']] = order
    return orderdict

def compileTradeHistory(fills,accs):
    tradeHistory = []
    for fill in fills:
        tradeHistory.append({'created_at': fill['created_at'],
                                'type': "fill",
                                'product_id': fill['product_id'],
                                'side': fill['side'],
                                'price': float(fill['price']),
                                'size': float(fill['size']),
                                'fee': float(fill['fee'])})

    for acc in accs:
        history = accs[acc]['history']
        if history: #check if history contains anything
            for transfer in history:
                tradeHistory.append({'created_at': transfer['created_at'],
                                        'type': "transfer",
                                        'currency': acc,
                                        'transfer_type': transfer['details']['transfer_type'],
                                        'amount': float(transfer['amount'])})
        
    tradeHistory = sorted(tradeHistory, key=lambda k: k['created_at'])
    return(tradeHistory)

def calcGainsBalancePrice(tradeHistory,currencies):
    startDay = ['2017-11-27T00:00:00.0Z']
    gains = {'time': startDay,'amount': [0.0]}
    balanceHistory = {'time': startDay} 
    avgPrice = {'time': startDay}
    for currency in currencies:
        balanceHistory[currency] = [0.0]
        avgPrice[currency] = [0.0]   

    #Price bought in at, including fees. Baked into script as done through Coinbase, not GDAX.
    avgPrice['ETH'] = [407.7671327]
    avgPrice['BTC'] = [9294.677104]
    avgPrice['LTC'] = [81.66727023]   

    i = 0 
    for trade in tradeHistory:
        if trade['type'] == "transfer":
            
            ProcessTransferTypeTrade(balanceHistory,avgPrice,gains,trade,currencies,i)
            i += 1

        elif trade['type'] == "fill":

            ProcessFillTypeTrade(balanceHistory,avgPrice,gains,trade,currencies,i) 
            i += 1
    return gains, balanceHistory, avgPrice

def ProcessTransferTypeTrade(balanceHistory,avgPrice,gains,trade,currencies,i):
    balanceHistory['time'].append(trade['created_at'])
    
    if trade['transfer_type'] == 'deposit':
        j = 1.0
    else: #else case for whatever Withdraw is referred to. 
        j = -1.0
        print('Personal Note: check transfer type naming below and change logic to identify it')
        print(trade['transfer_type'])
        sys.exit(1)

    balanceHistory[trade['currency']].append(balanceHistory[trade['currency']][i] + j*trade['amount'])
    
    for currency in currencies:
        if currency != trade['currency']:
            balanceHistory[currency].append(balanceHistory[currency][i])
        avgPrice[currency].append(avgPrice[currency][i])
    gains['amount'].append(gains['amount'][i]) 

def ProcessFillTypeTrade(balanceHistory,avgPrice,gains,trade,currencies,i):
    
    avgPrice['time'].append(trade['created_at'])
    gains['time'].append(trade['created_at'])

    baseCurrency, quoteCurrency = getBaseAndQuote(trade)
    size = trade['size'] #size of base currency
    price = trade['price'] #price of base currency in quote currency
    fee = trade['fee'] #fee in quote currency, paid on top of size*price
    #print(trade['product_id'],trade['side'],size,price,fee,size*price)

    updateBalanceHistory(balanceHistory,trade,baseCurrency,quoteCurrency,currencies,size,price,fee,i)

    if quoteCurrency == 'EUR' and trade['side'] == "sell":
        sellCoins(gains,baseCurrency,i,avgPrice,size,price,fee,currencies)
    
    elif quoteCurrency == 'EUR' and trade['side'] == "buy":
        buyCoins(gains,balanceHistory,baseCurrency,i,avgPrice,size,price,fee,currencies)

    elif quoteCurrency != 'EUR':
        exchangeCoins(gains,avgPrice,balanceHistory,trade,baseCurrency,quoteCurrency,currencies,size,price,fee,i)

def getBaseAndQuote(trade):
    pair = trade['product_id']
    pair = pair.split('-')
    baseCurrency = pair[0]
    quoteCurrency = pair[1]
    return baseCurrency, quoteCurrency

def updateBalanceHistory(balanceHistory,trade,baseCurrency,quoteCurrency,currencies,size,price,fee,i):

    balanceHistory['time'].append(trade['created_at'])
    if trade['side'] == "buy": #buying the base currency
        
        balanceHistory[baseCurrency].append(balanceHistory[baseCurrency][i] + size)
        balanceHistory[quoteCurrency].append(balanceHistory[quoteCurrency][i] - size*price - fee)
        
    elif trade['side'] == 'sell': #selling the base currency
        balanceHistory[baseCurrency].append(balanceHistory[baseCurrency][i] - size)
        balanceHistory[quoteCurrency].append(balanceHistory[quoteCurrency][i] + size*price - fee)

    for currency in currencies:
            if currency != baseCurrency and currency != quoteCurrency:
                balanceHistory[currency].append(balanceHistory[currency][i])

def buyCoins(gains,balanceHistory,baseCurrency,i,avgPrice,size,price,fee,currencies):
    #update price, gains have no change
    gains['amount'].append(gains['amount'][i])
    oldAmount = balanceHistory[baseCurrency][i]
    oldPrice = avgPrice[baseCurrency][i]
    newAmount = oldAmount + size
    avgPrice[baseCurrency].append(oldAmount*oldPrice/newAmount + ((size*price)+fee)/newAmount)

    for currency in currencies:
        if currency != baseCurrency:
            avgPrice[currency].append(avgPrice[currency][i])

def sellCoins(gains,baseCurrency,i,avgPrice,size,price,fee,currencies):
    #Then update gains
    oldGain = gains['amount'][i]
    oldPrice = avgPrice[baseCurrency][i]
    gains['amount'].append(oldGain + size*(price-oldPrice)-fee)

    #selling for EUR, therefore no price change, 
    #even if going to 0 balance (weight average of next calculation will still work as oldAmount = 0)
    for currency in currencies:
        avgPrice[currency].append(avgPrice[currency][i])

def exchangeCoins(gains,avgPrice,balanceHistory,trade,baseCurrency,quoteCurrency,currencies,size,price,fee,i):
    #update price of newly gained currency from buy or sell
    gains['amount'].append(gains['amount'][i])
    
    if trade['side'] == "buy":
        #gaining base in exchange for quote. Assess cost of quote in EUR, take this as cost of gaining base.
        
        oldAmount = balanceHistory[baseCurrency][i]
        oldPrice = avgPrice[baseCurrency][i]
        gainedAmount = size #base
        cost = size*price + fee #quote
        actualPrice = gainedAmount/cost #base.quote^-1
        effectiveEURPrice = avgPrice[quoteCurrency][i]/actualPrice #  EUR.quote^-1 / base.quote^-1 = EUR.quote^-1 x quote.base^-1 = EUR.base^-1
        newAmount = oldAmount + gainedAmount
        avgPrice[baseCurrency].append(oldPrice*oldAmount/newAmount + effectiveEURPrice*gainedAmount/newAmount)

        for currency in currencies:
            if currency != baseCurrency:
                avgPrice[currency].append(avgPrice[currency][i])

    else:
        oldAmount = balanceHistory[quoteCurrency][i] #of Y
        oldPrice = avgPrice[quoteCurrency][i] #of Y-EUR
        gainedAmount = size*price-fee #quote
        cost = size #base
        actualPrice = gainedAmount/cost #quote.base^-1
        effectiveEURPrice = avgPrice[baseCurrency][i]/actualPrice #EUR.base^-1/quote.base^-1 = EUR.base^-1 x base.quote^-1 = EUR.quote^-1
        newAmount = oldAmount + gainedAmount #of Y. size is in X, price is in Y.X^-1, fee is in Y
        avgPrice[quoteCurrency].append(oldPrice*oldAmount/newAmount + effectiveEURPrice*gainedAmount/newAmount)

        for currency in currencies:
            if currency != quoteCurrency:
                avgPrice[currency].append(avgPrice[currency][i])