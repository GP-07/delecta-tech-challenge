"""Every fixed value of the categorization: keyword vocabularies, confidences and thresholds.

The logic that applies them is in classification_business_rules.py (which rule decides an item, and with what
confidence) and keywords.py (how keywords are found in a text). The confidences and the embedding parameters were
tuned on the items labelled by hand (tests/fixtures/categorization); the tests check the measured accuracy.
"""

import re

# --- keywords (written normalised: lowercase, no accents) ------------------------------------------------------
#
# STRONG words name the kind of dish ("pizza", "hamburguesa", "coca cola"): they decide on their own.
# WEAK words name an ingredient ("pollo", "salmón", "queso"): they decide only when no strong word does, because
# "Ensalada de salmón" is a salad and "Hamburguesa de pollo" a burger.
# A plural ending (-s, -es) is accepted on the last word. A keyword starting with "^" only counts at the start of
# the text ("^salsa": "Salsa brava" is a sauce, "Pollo en salsa" is not).
# category name -> keywords. Ambiguous words are left out on purpose ("margarita" is a pizza and a cocktail,
# "sake" is salmon in sushi and a drink, "truita" is a trout and an omelette in Catalan).
STRONG_KEYWORDS: dict[str, tuple[str, ...]] = {
    # --- drinks
    "beer": ("cerveza", "cervesa", "beer", "birra", "estrella damm", "estrella galicia", "damm", "voll damm",
             "free damm", "mahou", "heineken", "moritz", "alhambra", "corona", "coronita", "san miguel", "cruzcampo",
             "amstel", "budweiser", "desperados", "leffe", "guinness", "peroni", "kirin", "asahi", "sapporo",
             "tsingtao", "kingfisher", "cobra", "efes", "keler", "inedit", "radler", "lager", "ipa", "paulaner",
             "pacifico", "modelo", "tiger", "brahma", "quilmes", "affligem", "grimbergen", "1906", "turia",
             "ambar", "bock", "estrella"),
    "tea": ("te", "tea", "chai", "matcha", "te verde", "te negro", "te rojo", "earl grey", "bubble tea"),
    "infusions": ("infusion", "infusio", "manzanilla", "poleo", "tila", "rooibos", "yerba mate", "yerba", "mate",
                  "tisana", "hierbaluisa"),
    "coffee": ("cafe", "coffee", "espresso", "expreso", "cortado", "capuccino", "cappuccino", "latte", "macchiato",
               "mocha", "moka", "frappuccino", "carajillo", "descafeinado", "cafe con leche", "flat white",
               "ristretto", "lungo", "cold brew", "cafe americano", "cafe solo", "nespresso", "capsulas"),
    "cocktails": ("cocktail", "coctel", "coctail", "mojito", "caipirinha", "caipiroska", "pina colada", "daiquiri",
                  "sangria", "spritz", "aperol", "gin tonic", "gintonic", "cubata", "cosmopolitan", "moscow mule",
                  "tinto de verano", "mimosa", "michelada", "pisco sour", "cuba libre", "long island", "negroni",
                  "bloody mary", "mai tai", "tequila sunrise"),
    "other espirituosas": ("whisky", "whiskey", "ron", "rum", "vodka", "ginebra", "gin", "tequila", "licor",
                           "orujo", "pacharan", "jagermeister", "baileys", "limoncello", "brandy", "cognac",
                           "absenta", "chupito", "soju", "mezcal", "hierbas", "ratafia", "aguardiente"),
    "soft drinks": ("coca cola", "cocacola", "cola", "fanta", "sprite", "7up", "seven up", "pepsi", "aquarius",
                    "nestea", "fuze tea", "fuzetea", "lipton", "ice tea", "iced tea", "trina", "trinaranjus",
                    "schweppes", "tonica", "kas", "bitter kas", "agua", "water", "aigua", "vichy", "font vella",
                    "bezoya", "solan de cabras", "lanjaron", "aquabona", "san pellegrino", "perrier", "red bull",
                    "monster", "burn", "refresco", "refresc", "soda", "gaseosa", "ginger ale", "ginger beer",
                    "dr pepper", "mirinda", "isotonica", "powerade", "gatorade", "jarritos", "inca kola", "malta",
                    "energy drink", "bebida energetica", "agua con gas", "agua mineral", "sin azucar"),
    "juice": ("zumo", "zumos", "jugo", "juice", "suc", "limonada", "lemonade", "zumo natural", "cold press",
              "granizado de limon", "mango simon", "nectar", "shot de jengibre"),
    "smoothie": ("smoothie", "batido", "milkshake", "shake", "lassi", "frappe", "batut"),
    "other drink": ("kombucha", "horchata", "orxata", "granizado", "granissat", "chicha", "agua de jamaica",
                    "agua fresca", "kefir", "bebida de avena", "bebida vegetal"),
    "generic drink": ("bebida", "drink", "beguda", "bebidas"),
    "tintos": ("vino tinto", "tinto", "red wine", "vi negre", "negre", "rioja", "ribera del duero", "ribera",
               "priorat", "montsant", "crianza", "garnacha", "tempranillo", "malbec", "merlot", "cabernet",
               "syrah", "pinot noir"),
    "blancos": ("vino blanco", "white wine", "vi blanc", "blanc", "blanco", "verdejo", "albarino", "rueda", "godello",
                "chardonnay", "sauvignon", "riesling", "xarel lo", "macabeo", "txakoli"),
    "rosados": ("vino rosado", "rosado", "rose wine", "vi rosat", "rosat"),
    "espumosos": ("cava", "champagne", "champan", "xampany", "prosecco", "brut", "lambrusco", "espumoso",
                  "sparkling"),
    "generosos": ("jerez", "oporto", "porto", "vermut", "vermouth", "vermu", "martini", "pedro ximenez", "amontillado",
                  "oloroso", "vino fino"),
    "dulces": ("moscatel", "moscato", "vino dulce", "vi dolc", "tokaji", "sauternes"),
    "generic wines": ("vino", "wine", "vi", "copa de vino", "vinos"),
    # --- fast food
    "burger": ("hamburguesa", "hamburgesa", "hamburguesas", "hamburgueses", "hamburger", "burger", "burguer",
               "whopper", "cheeseburger", "cheese burger", "big mac", "mcroyal", "smash", "smashburger",
               "mcchicken", "mccrispy", "mcextreme", "long chicken", "big king", "quarter pounder", "patty"),
    "sandwich": ("bocadillo", "bocata", "sandwich", "sandwitch", "entrepa", "entrepan", "bikini", "baguette",
                 "panini", "wrap", "bagel", "sub", "subs", "pepito", "chivito", "club sandwich", "flauta",
                 "mollete", "brascada", "serranito", "bocadillos", "croque monsieur", "piadina", "pita"),
    "kebab": ("kebab", "kebap", "doner", "durum", "shawarma", "gyros", "gyro", "lahmacun", "shish", "doner kebab",
              "plato kebab", "turkish pizza"),
    "hot dog": ("hot dog", "hotdog", "perrito", "perrito caliente", "frankfurt", "frankfurter"),
    "taco": ("taco", "tacos", "quesadilla", "fajita", "fajitas", "crunchywrap", "tostada mexicana",
             "sincronizada", "gringa", "chalupa", "gordita"),
    "burrito": ("burrito", "burritos", "enchilada", "chimichanga", "fajita wrap"),
    "empanada": ("empanada", "empanadilla", "empanadas", "salteña", "saltena", "pastelito"),
    "arepa": ("arepa", "arepas", "cachapa", "patacon"),
    "toasts": ("tostada", "toast", "torrada", "tosta", "bruschetta", "tostadas", "pan tostado"),
    # --- entrees
    "tapas": ("tapa", "patatas bravas", "bravas", "pimientos de padron", "padron", "callos", "ensaladilla",
              "ensaladilla rusa", "pan con tomate", "pa amb tomaquet", "mezze", "meze", "tabla de embutidos",
              "embutidos", "chopitos", "gambas al ajillo", "patatas al caliu"),
    "pinchos": ("pincho", "pintxo", "montadito", "gilda", "pinchito"),
    "nachos": ("nachos", "nacho", "tortilla chips", "totopos"),
    "fries": ("patatas fritas", "papas fritas", "fries", "french fries", "patatas deluxe", "patatas gajo", "gajos",
              "patatas", "papas", "patates", "chips", "patatas asadas", "patatas con queso", "yucas fritas",
              "yuca frita", "batata frita", "boniato frito", "cometas", "wedges"),
    "croquetas": ("croqueta", "croquetas", "croquetes", "croquette", "croquettes"),
    "other entrees": ("gyoza", "gyozas", "dumpling", "dim sum", "shaomai", "shumai", "siu mai", "har gow",
                      "rollito", "rollitos", "rollo primavera", "rollito primavera", "spring roll", "nem",
                      "wonton", "wan tun", "samosa", "pakora", "bhaji", "onion bhaji", "tequeno", "tequenos",
                      "bao", "baos", "aros de cebolla", "onion rings", "anillos de cebolla", "mozzarella sticks",
                      "palitos de mozzarella", "falafel", "lumpia", "takoyaki", "papadum", "papad", "pappadum",
                      "palitos de queso", "camembert frito", "queso frito", "bites", "jalapenos",
                      "poppers", "langos", "cheese sticks", "kibbeh", "kebbe", "nuggets vegetales", "rangoon",
                      "pan de gambas", "chips de gambas", "tempura de verduras", "entrante", "entrantes",
                      "starter", "starters", "aperitivo", "aperitivos", "para picar", "entrants"),
    "generic entrees": ("entrantes variados", "entrante variado", "surtido de entrantes", "entrantes del dia"),
    # --- pizza, pasta, rice
    "pizza": ("pizza", "pizzas", "pizze", "pizzes", "pinsa", "pizzeta", "pizzetta", "pizza familiar"),
    "calzone": ("calzone", "calzones", "pizza calzone"),
    "lasagna": ("lasana", "lasagna", "lasagne", "lasanya"),
    "canelones": ("canelones", "canelon", "canelons", "cannelloni", "canalons"),
    "fideua": ("fideua", "fideuada"),
    "noodles": ("noodles", "noodle", "fideos", "fideo", "tallarines", "tallarin", "ramen", "udon", "yakisoba",
                "yaki soba", "yaki udon", "soba", "pad thai", "chow mein", "lo mein", "pho", "fideos de arroz",
                "fideos chinos", "mee goreng", "bihon", "japchae", "laksa"),
    "pasta varieties": ("spaghetti", "espaguetis", "espagueti", "spaguetti", "macarrones", "macarrons",
                        "maccheroni", "penne", "rigatoni", "tagliatelle", "fettuccine",
                        "fettuccini", "linguine", "tortellini", "tortelloni", "ravioli", "raviolis", "reviolis",
                        "gnocchi", "noquis", "pappardelle", "fusilli", "farfalle", "mac and cheese", "mac n cheese",
                        "paccheri", "bucatini", "orecchiette", "trofie", "strozzapreti", "cappelletti",
                        "agnolotti", "mezzelune", "fiocchi", "tallarines italianos"),
    "generic pasta": ("pasta", "pastas", "pasta fresca", "plato de pasta"),
    "paella": ("paella", "paellas", "paella mixta", "paella de marisco", "paella valenciana"),
    "risotto": ("risotto", "risoto", "risottos"),
    "mediterranean rice": ("arroz negro", "arros negre", "arroz a banda", "arros a banda", "arroz caldoso",
                           "arros caldos", "arroz meloso", "arroz del senyoret", "arros del senyoret",
                           "arroz de marisco", "arroz al horno", "arros al forn", "arroz con bogavante"),
    "other rice": ("biryani", "biriyani", "arroz frito", "arroz tres delicias", "tres delicias", "chaufa",
                   "bibimbap", "donburi", "gyudon", "gyuu don", "katsudon", "oyakodon", "chashu don",
                   "pilaf", "pulao", "pulav", "arroz con pollo", "nasi goreng", "arroz blanco", "arroz basmati",
                   "arroz cantones", "arroz yakimeshi", "yakimeshi", "arroz salteado", "rice bowl", "arroz chino",
                   "arroz jazmin", "arroz con leche de coco", "kabsa", "mandi", "calentado"),
    "generic rice": ("arroz", "arros", "rice", "arroces"),
    # --- other dishes
    "salads": ("ensalada", "ensaladas", "salad", "salads", "amanida", "amanides", "ensalades", "insalata",
               "cesar salad"),
    "poke": ("poke", "pokes", "poke bowl", "poké"),
    "sushi": ("sushi", "maki", "makis", "uramaki", "uramakis", "nigiri", "nigiris", "niguiri", "niguiris",
              "sashimi", "sashimis", "temaki", "temakis", "gunkan", "gunkans", "hosomaki", "futomaki",
              "california roll", "california", "roll", "rolls", "chirashi", "dragon roll", "crunch roll",
              "philadelphia roll", "tartar de salmon", "onigiri", "piezas sushi", "sushi mixto"),
    "sauces": ("^salsa", "^salsas", "^sauce", "^sobre", "alioli", "allioli", "all i oli", "ketchup", "mayonesa",
               "maionesa", "mayo", "mostaza", "mustard", "guacamole", "chimichurri", "raita", "chutney",
               "salsa brava", "salsa barbacoa", "salsa de soja", "salsa soja", "salsa picante", "salsa rosa",
               "salsa tartara", "salsa agridulce", "romesco", "pesto", "salsa de queso", "salsa extra",
               "extra salsa", "dip", "dips", "tahini", "tahina", "sriracha", "salsa teriyaki", "harissa",
               "mojo picon", "salsa yogur"),
    "omelette": ("tortilla", "tortilla de patatas", "tortilla espanola", "tortilla francesa", "omelette",
                 "omelet", "truita de patates", "truita francesa", "frittata"),
    "eggs": ("huevos rotos", "huevos estrellados", "huevos fritos", "huevo frito", "huevos revueltos",
             "huevo poche", "huevos benedict", "benedict", "huevos rancheros", "shakshuka", "huevo trufado",
             "huevos", "huevo"),
    "bread": ("naan", "nan", "garlic naan", "cheese naan", "chapati", "roti", "paratha", "parantha", "parotta",
              "kulcha", "pan de ajo", "garlic bread", "pan de pita", "pan pita", "pan", "panecillo", "focaccia",
              "pan bao", "pan artesano", "pan de cristal", "pa de vidre", "chapata", "barra de pan", "hogaza",
              "pan de molde", "pita bread", "pan naan", "panaderia", "bakery", "fleca", "forn de pa"),
    "vegetable soups and creams": ("sopa", "soup", "crema de", "gazpacho", "salmorejo", "caldo", "consome",
                                   "miso", "sopa de miso", "misoshiru", "pure", "vichyssoise", "minestrone",
                                   "harira", "porrusalda", "escudella", "crema de verduras", "crema de calabaza",
                                   "tom yum", "tom kha"),
    "legumes": ("lentejas", "lentils", "garbanzos", "chickpeas", "alubias", "judias", "frijoles", "dal", "daal",
                "dhal", "tarka dal", "chana", "chana masala", "chole", "edamame", "hummus", "humus", "houmous",
                "mongetes", "cigrons", "fabada", "rajma"),
    "nuts and seeds": ("frutos secos", "fruits secs", "nueces", "almendras", "cacahuetes", "pistachos",
                       "anacardos", "pipas", "nuts", "avellanas", "kikos", "semillas"),
    "fruit": ("fruta", "fruit", "macedonia", "fruta del tiempo", "fruta de temporada", "fruta fresca",
              "fresas con nata", "fruta cortada", "brocheta de fruta"),
    "generic vegetables": ("verduras", "verdura", "vegetales", "vegetables", "verdures", "mixed vegetable",
                           "mixed vegetables", "verduras variadas", "parrillada de verduras",
                           "verduras salteadas", "verduras a la plancha"),
    # --- sweets and dairy
    "ice cream": ("helado", "helados", "gelato", "gelat", "gelats", "ice cream", "sundae", "mcflurry", "magnum",
                  "ben and jerry", "ben and jerrys", "haagen dazs", "haagen dasz", "tarrina", "cucurucho",
                  "polo", "frigo", "kulfi", "affogato", "copa de helado", "cornetto", "crocanti"),
    "sorbet": ("sorbete", "sorbet", "sorbetto"),
    "cakes": ("tarta", "tartas", "pastel", "cake", "cakes", "cheesecake", "tiramisu", "brownie", "bizcocho",
              "coulant", "carrot cake", "sacher", "red velvet", "tarta de queso", "pie", "plum cake", "plumcake",
              "banoffee", "pastis", "selva negra", "pionono", "torta", "cupcake", "cupcakes", "soufflé",
              "souffle", "volcan de chocolate"),
    "cookies": ("cookie", "cookies", "galleta", "galletas", "galeta", "galetes", "macaron", "macarons", "alfajor",
                "alfajores", "biscuit", "biscotti", "carquinyolis", "polvoron"),
    "chocolate": ("chocolate", "chocolates", "bombon", "bombones", "trufas de chocolate", "nutella", "kinder",
                  "kit kat", "tableta", "xocolata", "cacao", "chocolatina"),
    "pastries": ("croissant", "croissants", "cruasan", "bolleria", "ensaimada", "donut", "donuts", "dunkin",
                 "dunkins", "muffin", "muffins", "magdalena", "magdalenas", "palmera", "churro", "churros",
                 "berlina", "caracola", "napolitana de chocolate", "pain au chocolat", "cinnamon roll", "baklava",
                 "bunuelo", "bunuelos", "hojaldre", "strudel", "xuixo", "eclair", "profiteroles", "medialuna",
                 "medialunas", "palmerita", "rosquilla", "pastelitos", "danish", "bollo", "bollos", "brioche",
                 "trenza", "cronut", "panettone"),
    "waffles": ("gofre", "gofres", "waffle", "waffles"),
    "pancakes": ("tortita", "tortitas", "pancake", "pancakes", "hotcakes", "hot cakes", "crumpet"),
    "crepes": ("crepe", "crepes", "crep", "creps", "crepa", "crepas"),
    "other sweets": ("mochi", "mochis", "flan", "natillas", "crema catalana", "arroz con leche", "panna cotta",
                     "pannacotta", "mousse", "gulab jamun", "ras malai", "rasmalai", "kheer", "turron",
                     "membrillo", "dulce de leche", "postre de", "tiramisu de", "overnight oats", "pudding",
                     "pudin", "cuajada", "leche frita", "torrija", "torrijas", "dulce de coco", "dorayaki",
                     "mato", "suspiro", "tres leches", "brigadeiro", "creme brulee", "copa", "parfait",
                     "chia pudding", "granola"),
    "generic sweets": ("postre", "postres", "dessert", "desserts", "postre del dia", "dulce", "dulces", "dolc"),
    "yogurs": ("yogur", "yogurt", "yoghurt", "iogurt", "yogures", "yogurts", "greek bowl", "frozen yogurt"),
    "milk": ("leche", "milk", "llet", "leche de coco", "leche de avena", "leche de almendra", "bebida de soja",
             "cola cao", "colacao", "nesquik"),
    "cheese": ("tabla de quesos", "plato de quesos", "paneer", "palak paneer", "saag paneer"),
}

WEAK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "chicken": ("pollo", "chicken", "pollastre", "alitas", "alas de pollo", "wings", "nuggets", "mcnuggets",
                "pechuga", "muslo", "muslos", "contramuslo", "tandoori", "tikka", "tori", "tenders", "tiras de pollo",
                "crispy chicken", "pollo frito", "pollo asado", "pollo a l ast", "a l ast", "katsu", "karaage",
                "yakitori", "tawuk", "tavuk", "pollito", "palomitas de pollo", "pinchos de pollo", "chilly chicken",
                "chilli chicken", "pollo al curry", "chicken curry", "pollo tikka"),
    "beef": ("ternera", "beef", "vedella", "buey", "vaca", "vacuno", "entrecot", "entrecote", "solomillo",
             "chuleton", "bistec", "bisteck", "steak", "picanha", "vacio", "bife", "rib eye", "ribeye",
             "carne picada", "rabo de toro", "carrillada", "milanesa", "gyu", "wagyu", "chuleta de vaca",
             "lomo saltado", "churrasco", "roast beef", "karahi"),
    "pork": ("cerdo", "pork", "porc", "secreto", "presa", "lomo", "costilla", "costillas", "ribs", "panceta",
             "bacon", "beicon", "cochinillo", "pulled pork", "jamon", "pernil", "chorizo", "butifarra", "botifarra",
             "salchicha", "salchichas", "salsitxa", "longaniza", "chistorra", "torrezno", "torreznos",
             "chicharron", "carnitas", "char siu", "chashu", "codillo", "lacon", "sobrasada", "fuet", "salchichon",
             "mortadela", "mortadella", "pepperoni", "salami", "prosciutto", "speck", "tonkatsu", "krakoski"),
    "lamb": ("cordero", "lamb", "xai", "mutton", "cabrito", "chuletillas", "paletilla", "chanp", "gosht", "kofta",
             "kofte", "cordero tikka", "seekh"),
    "duck": ("pato", "duck", "anec", "magret", "confit de pato", "pato laqueado"),
    "rabbit": ("conejo", "conill", "rabbit"),
    "generic meats": ("albondigas", "carne", "carnes", "meat", "carn", "parrillada", "parrillada de carne",
                      "mixed grill", "barbecue", "barbacoa mixta", "carne mixta", "mixto", "asado", "brasa",
                      "a la brasa", "special barbecue"),
    "other meats": ("pavo", "turkey", "jabali", "ciervo", "venado", "codorniz", "foie", "higado",
                    "perdiz", "oca", "avestruz", "canguro", "cecina"),
    "salmon": ("salmon", "salmo", "sake", "salmon ahumado", "smoked salmon"),
    "tuna": ("atun", "tuna", "tonyina", "maguro", "toro", "bonito del norte", "tataki de atun"),
    "prawn": ("gamba", "gambas", "gambes", "langostino", "langostinos", "prawn", "prawns", "shrimp", "ebi",
              "camaron", "camarones", "carabinero", "cigala", "cigalas", "gambetes"),
    "squid": ("calamar", "calamares", "calamars", "squid", "chipiron", "chipirones", "puntillitas", "ika",
              "rabas"),
    "octopus": ("pulpo", "octopus", "tako"),
    "cuttlefish": ("sepia", "cuttlefish", "choco", "chocos", "sipia"),
    "mussels": ("mejillon", "mejillones", "musclo", "musclos", "mussels", "mussel"),
    "clams": ("almeja", "almejas", "clams", "cloïsses", "cloisses", "vongole", "berberechos"),
    "anchovy": ("anchoa", "anchoas", "boqueron", "boquerones", "anchovy", "anchovies", "seitons"),
    "cod": ("bacalao", "bacalla", "cod", "skrei"),
    "sea bass": ("lubina", "sea bass", "llobarro", "suzuki", "branzino", "corvina"),
    "monkfish": ("rape", "monkfish", "rap"),
    "turbot": ("rodaballo", "turbot", "remol"),
    "other fish": ("dorada", "orada", "merluza", "lluc", "sardina", "sardinas", "trucha", "lenguado", "emperador",
                   "pez espada", "caballa", "bonito", "anguila", "unagi", "hamachi", "pez limon", "pez mantequilla",
                   "tilapia", "pangasio", "mero", "besugo", "salmonete", "dorado"),
    "generic fish": ("pescado", "fish", "peix", "pescaito", "pescados", "fish curry", "pescado frito"),
    "other seafood": ("cangrejo", "crab", "surimi", "bogavante", "langosta", "vieira", "vieiras", "ostra", "ostras",
                      "zamburinas", "navajas", "nécoras", "necoras", "kani", "palitos de cangrejo", "erizo",
                      "percebes"),
    "generic seafood": ("marisco", "mariscos", "seafood", "marisc", "frutos del mar", "ceviche mixto",
                        "leche de tigre"),
    "other vegetables": ("berenjena", "berenjenas", "espinacas", "champinones", "champinon", "setas", "alcachofa",
                         "alcachofas", "esparragos", "pimientos", "pimiento", "calabacin", "brocoli", "coliflor",
                         "kimchi", "aloo gobi", "allu gobhi", "aloo", "bhindi", "okra", "saag", "palak",
                         "melanzane", "parmigiana de melanzane", "escalivada", "pisto", "ratatouille", "tofu",
                         "heura", "seitan", "tempeh", "pav bhaji", "baingan", "mushroom", "mushrooms", "zanahoria",
                         "calabaza", "patata asada", "boniato", "yuca", "aguacate", "tomate", "judias verdes"),
    "fruit": ("fresa", "fresas", "platano", "banana", "mango", "pina", "manzana", "pera", "melon", "sandia",
              "kiwi", "naranja", "frutos rojos", "arandanos", "frambuesa", "maracuya", "coco", "papaya"),
    "cheese": ("queso", "quesos", "cheese", "formatge", "burrata", "provolone", "camembert", "brie", "manchego",
               "mozzarella", "cheddar", "gorgonzola", "parmesano", "emmental", "gouda", "provola", "feta",
               "queso de cabra", "cabra", "requeson", "ricotta", "mascarpone", "halloumi", "taleggio"),
    "pasta varieties": ("carbonara", "bolonesa", "bolognesa", "amatriciana", "arrabbiata", "puttanesca",
                        "pomodoro", "alfredo", "cacio e pepe", "aglio olio"),
    "sushi": ("piezas", "pzs", "pzas", "tempura roll"),
    "omelette": ("truita",),
    "eggs": ("egg", "eggs", "ou", "ous"),
    "toasts": ("tostado",),
}

# Things on a menu that are not food nor drink (they get no category).
NON_FOOD_WORDS = ("palillos", "cubiertos", "bolsa", "bolsas", "servilleta", "servilletas", "propina", "gastos de envio",
            "envio", "packaging", "envase", "tupper", "taper", "merchandising", "camiseta", "gorra", "taza",
            "tarjeta regalo", "gift card", "vaso reutilizable", "cubitos de hielo", "hielo", "bolsa de hielo",
            "velas", "vela", "mechero", "encendedor", "tabaco", "toallitas", "cuchara", "tenedor", "plato vacio",
            "kit de palillos", "coffee bags", "merch", "llavero", "mascarilla", "termo")
# Menu and combo words: a combo is classified by its main dish.
COMBO_WORDS = ("menu", "menus", "combo", "combos", "pack", "packs", "box", "promo", "promocion", "2x1", "3x2", "duo",
         "mcmenu", "sharebox", "kids menu")
# Words that make an item generic within its section ("Postre del día", "Surtido de entrantes").
GENERIC_WORDS = ("del dia", "de la casa", "variado", "variados", "variada", "variadas", "surtido", "surtidos", "mix",
           "seleccion", "selection", "degustacion", "assorted", "del chef", "de temporada")

# Where the dish itself ends and its side dishes or extras begin: "Pollo asado | con patatas", "Pizza | + bebida".
CONNECTORS = frozenset({"con", "amb", "with", "y", "i", "e", "and", "mas", "+", ",", "acompanado", "acompanada",
                        "acompanados", "acompanadas"})
PLURAL_ENDINGS = ("", "s", "es")
COMBO_SEPARATOR = "+"  # "Pizza + bebida": a "+" in a name makes it a combo
ANCHOR = "^"  # prefix of a keyword that only counts at the start of the text

APOSTROPHES = re.compile(r"[’'´`]")
# Anything but letters, digits, "+" and ",": "+" and "," are kept because they separate a dish from its extras.
NOT_TEXT = re.compile(r"[^a-z0-9+,]+")

# --- confidence of each rule (see classification_business_rules) ------------------------------------------------

STRONG_NAME_CONFIDENCE = 0.95  # 1. a strong keyword in the head of the name
NON_FOOD_CONFIDENCE = 0.9  # 2. a non-food word in the name
SECTION_CONFIDENCE = 0.85  # 3. a strong keyword in the section (also a generic one, after rules 4 and 5)
WEAK_NAME_CONFIDENCE = 0.75  # 4. a weak keyword in the head of the name
REST_OF_NAME_CONFIDENCE = 0.65  # 5. a keyword in the rest of the name
COMBO_DESCRIPTION_CONFIDENCE = 0.6  # 6. for a combo, a keyword in the head of its description
EMBEDDING_WEIGHT = 0.5  # 7. the similarity of the most similar reference, times this
WEAK_SECTION_CONFIDENCE = 0.4  # 8. a weak section ("Entrantes", "Tapas", "Pollo")

LOW_CONFIDENCE = 0.6  # below it, a classification is a guess worth reviewing
REFERENCE_CONFIDENCE = 0.85  # rule decisions good enough to teach the embeddings
ENTREES = "entrees"  # parent of course words ("Entrantes", "Tapas"): as a section they say little about the dish
OTHER_PREFIX = "other"  # a section category becomes its "other" sibling for a concrete dish ("other sweets")

# --- embeddings ------------------------------------------------------------------------------------------------

# Measured on the labelled items: a similarity of 0.7, 5 neighbours and up to 120 references per category gave the
# best results; more references cost time and added nothing.
MIN_SIMILARITY = 0.7
NEIGHBOURS = 5
REFERENCES_PER_CATEGORY = 120
EMBEDDING_BATCH_SIZE = 256
MAX_DESCRIPTION_CHARACTERS = 200  # of the description, in the text that is embedded

# --- taxonomy file (food_categories.xlsx) ------------------------------------------------------------------------

TAXONOMY_HEADER = ("uidentifier", "family", "name", "parent", "is_generic_or_other")
TAXONOMY_MAX_BYTES = 5 * 1024 * 1024
TAXONOMY_MAX_ROWS = 5000
GENERIC_PREFIX = "generic "
