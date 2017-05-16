import olx

tc = olx.olxChecker(database='mondeo.db')
tc.updateDatabase()
tc.save('mondeo.db')
