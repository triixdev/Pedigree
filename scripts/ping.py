from pedigree.db import connect

db = connect()
g = db.select_graph("ping")
g.query("CREATE (:Test {name: 'hello'})")
print(g.query("MATCH (t:Test) RETURN t.name").result_set)
g.delete()
