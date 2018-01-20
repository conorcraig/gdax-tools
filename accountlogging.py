import csv

def writeDictOfListsToCSV(dictVar,filename):
    with open(filename, "w",newline='') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(list(dictVar.keys()))
        writer.writerows(zip(*dictVar.values()))

def writeListOfDictsToCSV(listVar,key,value,filename):
    first = True
    with open(filename, "w",newline='') as outfile:
        writer = csv.writer(outfile)
        for item in listVar:
            if item[key] == value:
                if first:
                    writer.writerow(list(item.keys()))
                    first = False
                writer.writerow(item.values())

def logData(gains,avgPrice,balanceHistory,tradeHistory):

    writeDictOfListsToCSV(gains,"logs/gains.csv")
    writeDictOfListsToCSV(avgPrice,"logs/price.csv")
    writeDictOfListsToCSV(balanceHistory,"logs/balance.csv")
    writeListOfDictsToCSV(tradeHistory,'type',"transfer","logs/transfer.csv")
    writeListOfDictsToCSV(tradeHistory,'type',"fill","logs/fills.csv")