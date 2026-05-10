from django.db import models
from django.db.models import Q
from django.contrib.postgres.indexes import GinIndex

import re
import json
from rdflib import Graph, Literal, URIRef, RDF, RDFS, Namespace, BNode

class TxtSource(models.Model):
    abbr = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=1000)
    url = models.URLField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.title

class Pos(models.Model):
    PTYPES = {
        "COM": "Common",
        "PROP": "Proper nouns"
    }
    abbr = models.CharField(max_length=5)
    term = models.CharField(max_length=50)
    type = models.CharField(max_length=5, choices=PTYPES)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.term

class Tag(models.Model):
    TAGTS = {
        "GR": "Grammar",
        "CO": "Content",
        "SO": "Source",
        "WL": "Word list",
        "SH": "Sign Shape"
    }
    term = models.CharField(max_length=200)
    type = models.CharField(choices=TAGTS, max_length=200)
    definition = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.term

class Lemma(models.Model):
    STATUSES = {
        "NR": "not reviewed",
        "R": "reviewed",
        "RD": "reviewed and documented"
    }

    SORTS = {
        "ŋ": "gz",
        "š": "sz",
        "ř": "rz",
        "ḫ": "hz"
    }

    status = models.CharField(choices=STATUSES, default="NR", max_length=5)
    cf = models.CharField(max_length=200)
    pos = models.ForeignKey(Pos, blank=True, null=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, through="LemmaTag", blank=True)
    components = models.ManyToManyField("self", symmetrical=False, blank=True)
    sortform = models.CharField(max_length=200)

    def base_spelling(self) -> "Spelling":
        if baseform := Form.objects.filter(lemma=self, base=True).first():
            return Spelling.objects.filter(form=baseform).first()
        else:
            firstform = Form.objects.filter(lemma=self).first()
            return Spelling.objects.filter(form=firstform).first()

    def emesal_spelling(self) -> "Spelling":
        emeform = Form.objects.filter(lemma=self, formtype__term="emesal").first()
        return Spelling.objects.filter(form=emeform).first()
    
    def emesal_form(self) -> "Form":
        return Form.objects.filter(lemma=self, formtype__term="emesal").first()

    def make_sortform(self) -> str:
        sortform = self.cf.lower()
        for source, target in self.SORTS.items():
            sortform = re.sub(source, target, sortform)

        return sortform

    def update_sortform(self) -> None:
        self.sortform = self.make_sortform()

    def change_h(self):
        newcf = re.sub("h", "ḫ", self.cf)
        newcf = re.sub("H", "Ḫ", newcf)

        self.cf = newcf

    def merge_lem(self, duplicate: "Lemma"):
        """Merges oids, definitions, forms, and components (if any)
        from ::duplicate:: into self.
        """
        own_components = self.components.count()
        dup_components = duplicate.components.count()
        if (own_components == dup_components) and (own_components > 0):
            dup_cs = set([c for c in duplicate.components.all()])
            own_cs = set([c for c in self.components.all()])
            if not own_cs == dup_cs:
                print("All lemma components must match to merge")
                exit()
            print("All components match")
        elif (own_components > 0 and dup_components == 0) or (own_components == 0 and dup_components > 0):
            print("Cannot merge compound lemma with non-compound lemma")
            exit()
        elif own_components == 0 and dup_components == 0:
            print("No components")

        for oid in duplicate.lemmaoid_set.filter(
            ~Q(oid__in=[e for e in self.lemmaoid_set.all()])
        ):
            newoid = LemmaOid(
                lemma=self,
                oid=oid
            )
            newoid.save()

        for lemdef in duplicate.definitions.all():
            lemdef.lemma=self
            lemdef.save()

        for form in duplicate.forms.all():
            form.lemma=self
            form.save()

        part_ofs = Lemma.objects.filter(components=duplicate)
        for part_of in part_ofs:
            part_of.components.add(self)
            part_of.components.remove(duplicate)
            part_of.save()

        # duplicate.delete()

    def _make_rdf(self, lem_uri) -> Graph:
        ONTOLEX = Namespace("http://www.w3.org/ns/lemon/ontolex#")
        LEXINFO = Namespace("http://www.lexinfo.net/ontology/3.0/lexinfo#")

        g = Graph()
        g.bind("ontolex", ONTOLEX)
        g.bind("lexinfo", LEXINFO)

        lemuri = URIRef(lem_uri)

        if self.components.count() > 0:
            ltype = ONTOLEX.MultiwordExpression
        else:
            ltype = ONTOLEX.Word

        match self.pos.term:
            case "verb":
                g.add((lemuri, LEXINFO.partOfSpeech, LEXINFO.Verb))
            case "noun":
                g.add((lemuri, LEXINFO.partOfSpeech, LEXINFO.Noun))
            case _:
                ...

        g.add((lemuri, RDF.type, ltype))
        g.add((lemuri, RDFS.label, Literal(self.cf)))

        for form in self.forms.all():
            formuri = BNode()
            g.add((lemuri, ONTOLEX.lexicalform, formuri))
            g.add((formuri, RDF.type, ONTOLEX.Form))
            g.add((formuri, RDFS.label, Literal(form.cf)))

        return g

    def make_jsonld(self, lem_uri):
        context = {
            "lexinfo": "http://www.lexinfo.net/ontology/3.0/lexinfo#",
            "ontolex": "http://www.w3.org/ns/lemon/ontolex#",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
        }
        return json.loads(self._make_rdf(lem_uri).serialize(format="json-ld", context=context))

    def make_ttl(self, lem_uri) -> str:
        return self._make_rdf(lem_uri).serialize(format="ttl")
    
    class Meta:
        indexes = [
            GinIndex(fields=["cf"], name="cf_trgm", opclasses=["gin_trgm_ops"]),
            GinIndex(fields=["sortform"], name="sort_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self) -> str:
        return f"{self.cf} ({self.pk})"

class LemmaOid(models.Model):
    lemma = models.ForeignKey(Lemma, on_delete=models.CASCADE)
    oid = models.CharField(max_length=20, blank=True)

    def __str__(self) -> str:
        return self.oid

class LemmaCitation(models.Model):
    lemma = models.ForeignKey(Lemma, on_delete=models.CASCADE)
    citation = models.CharField(max_length=1000)
    gloss = models.CharField(max_length=1000, blank=True)
    trans = models.CharField(max_length=1000, blank=True)
    lines = models.CharField(max_length=100, blank=True)
    source = models.ForeignKey(TxtSource, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self) -> str:
        return self.citation

class LemmaDef(models.Model):
    lemma = models.ForeignKey(Lemma, on_delete=models.CASCADE, related_name="definitions")
    definition = models.TextField()

    def __str__(self) -> str:
        return self.definition

class LemmaTag(models.Model):
    lemma = models.ForeignKey(Lemma, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    citation = models.TextField(blank=True)
    tagsource = models.ForeignKey(TxtSource, blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self) -> str:
        return self.lemma.cf + ": " + self.tag.term

class FormType(models.Model):
    term = models.CharField(max_length=200)
    definition = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.term

class Form(models.Model):
    lemma = models.ForeignKey(Lemma, on_delete=models.CASCADE, related_name="forms")
    cf = models.CharField(max_length=200, blank=True)
    formtype = models.ManyToManyField(FormType, blank=True)
    base = models.BooleanField(default=False)

    class Meta:
        indexes = [
            GinIndex(
                fields=["cf"],
                name="formcf_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self) -> str:
        return self.cf

# class Sign(models.Model):
#     transcription = models.CharField(max_length=200)
#     cuneiform = models.CharField(max_length=10, blank=True)
#     oid = models.CharField(max_length=10, blank=True)
#     note = models.TextField(blank=True)

#     def __str__(self):
#         return self.transcription

# class SignReading(models.Model):
#     sign = models.ForeignKey(Sign, on_delete=models.CASCADE)
#     reading = models.CharField(max_length=200)
#     note = models.CharField(max_length=200, blank=True)

#     def __str__(self):
#         return self.reading

class Spelling(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="spellings")
    spelling_lat = models.CharField(max_length=200)
    spelling_cun = models.CharField(max_length=200, blank=True)
    # signs = models.ManyToManyField(Sign, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [
            GinIndex(
                fields=["spelling_lat"],
                name="spelling_lat_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self) -> str:
        return self.spelling_lat
