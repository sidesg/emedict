from typing import Any
from django.db.models.query import QuerySet
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import generic
from django.db.models import Q
from django.core.paginator import Paginator
from django.core.paginator import EmptyPage
from django.core.paginator import PageNotAnInteger

import elasticsearch.dsl as edsl

from rest_framework import viewsets

from .forms import LemmaInitialLetterForm, LemmaFacetForm, LemmaAdvancedSearchForm, SearchFacetForm
from .models import Lemma, Tag, FormType, Form, TxtSource, Pos
from .serializers import LemmaSerializer
from .documents import LemmaDocument

LEMMA_PAGINATION = 40

class TagIdView(generic.DetailView):
    model = Tag
    template_name = "emedict/tags_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lemmata"] = Lemma.objects.filter(tags__id=self.kwargs['pk']).order_by("sortform")

        return context

class LemmaListView(generic.FormView):
    template_name = "emedict/lemma_home.html"

    def get(self, request, *args, **kwargs):
        form = LemmaInitialLetterForm(self.request.GET or None)
        selected_poss = None
        selected_tags = None
        initial = "A"

        #declare variables for initial landing on list page
        query_set = Lemma.objects.filter(
            Q(cf__startswith="A") | Q(cf__startswith="a"),
            pos__type="COM"
        ).order_by("sortform")

        possible_poss = Pos.objects.filter(id__in=query_set.values("pos"))
        possible_tags = Tag.objects.filter(id__in=query_set.values("tags"))

        if form.is_valid():
            initial = request.GET.get("initial", "A")
            selected_poss = request.GET.getlist("poss")
            selected_tags = request.GET.getlist("tags")

            query_set = Lemma.objects.filter(
                Q(cf__startswith=initial.lower()) | Q(cf__startswith=initial.upper()),
                pos__type="COM"
            ).order_by("sortform")

            possible_poss = Pos.objects.filter(id__in=query_set.values("pos"), type="COM")
            possible_tags = Tag.objects.filter(id__in=query_set.values("tags"))

            if selected_poss:
                query_set = query_set.filter(
                    Q(pos__term__in=selected_poss),
                    pos__type="COM"
                ).distinct().order_by("sortform")
            if selected_tags:
                query_set = query_set.filter(
                    Q(tags__term__in=selected_tags),
                    pos__type="COM"
                )

        paginator = Paginator(query_set, LEMMA_PAGINATION)
        page = request.GET.get('page')
        try:
            query_set = paginator.page(page)
        except PageNotAnInteger:
            query_set = paginator.page(1)
        except EmptyPage:
            query_set = paginator.page(paginator.num_pages)

        facet_form = LemmaFacetForm(
            possible_poss,
            possible_tags,
            initial={
                "initial": initial if initial else "A",
                "tags":selected_tags,
                "poss":selected_poss
            },
        )

        return self.render_to_response(self.get_context_data(
            form=form, 
            lemmalist=query_set, 
            sidebar_form=facet_form, 
            lem_search_form=LemmaAdvancedSearchForm
        ))

class LemmaSearchView(generic.FormView):
    template_name = "emedict/lemma_search.html"

    def get(self, request, *args, **kwargs):
        form = LemmaAdvancedSearchForm(self.request.GET or None)

        if form.is_valid():
            term = request.GET["search_term"]
            term_type = request.GET["search_type"]
            selected_poss = request.GET.getlist("poss", None)
            selected_tags = request.GET.getlist("tags", None)

            match term_type:
                case "lemma":
                    # fields = [
                    #     "cf", "forms__cf", "forms.spellings__spelling_lat", "sortform"
                    # ]
                    q = (
                        edsl.Q(
                            "multi_match",
                            query = term,
                            fields =  ["cf, sortform"]
                        ) |
                        edsl.Q(
                            "nested",
                            path="forms",
                            query=edsl.Q(
                                "match",
                                forms__cf=term
                            )
                        ) |
                        edsl.Q(
                            "nested",
                            path="forms",
                            query=edsl.Q(
                                "nested",
                                path="forms.spellings",
                                query=edsl.Q(
                                    "match",
                                    forms__spellings__spelling_lat=term
                                )
                            )
                        )
                    )                
                case "definition":
                    # fields = ["definitions__definition"]
                    q = edsl.Q(
                        "nested",
                        path="definitions",
                        query=edsl.Q(
                            "match",
                            definitions__definition=term
                        )                      
                    )
                case _:
                    q = (
                        edsl.Q(
                            "multi_match",
                            query = term,
                            fields =  ["cf, sortform"]
                        ) |
                        edsl.Q(
                            "nested",
                            path="forms",
                            query=edsl.Q(
                                "match",
                                forms__cf=term
                            )
                        ) |
                        edsl.Q(
                            "nested",
                            path="forms",
                            query=edsl.Q(
                                "nested",
                                path="forms.spellings",
                                query=edsl.Q(
                                    "match",
                                    forms__spellings__spelling_lat=term
                                )
                            )
                        )
                    )
            # TODO: convert sub nums to regular?
            search = LemmaDocument.search().extra(size=100).query(q)
            query_set: QuerySet = search.to_queryset()
            query_set = query_set.distinct()
            
            possible_poss = Pos.objects.filter(id__in=query_set.values("pos"), type="COM")
            possible_tags = Tag.objects.filter(id__in=query_set.values("tags"))

            if selected_poss:
                query_set = query_set.filter(
                    Q(pos__term__in=selected_poss),
                    pos__type="COM"
                ).distinct().order_by("sortform")
            if selected_tags:
                query_set = query_set.filter(
                    Q(tags__term__in=selected_tags),
                    pos__type="COM"
                )

            facet_form = SearchFacetForm(
                possible_poss,
                possible_tags,
                initial={
                    "search_term": term,
                    "search_type":term_type,
                    "tags":selected_tags,
                    "poss":selected_poss
                },
            )
    
        return self.render_to_response(self.get_context_data(
            lemmalist=query_set,
            form=LemmaInitialLetterForm,
            lem_search_form=form,
            sidebar_form=facet_form
        ))

def index(request):
    return render(request, "emedict/emedict.html")

def lemma_json(request, pk):
    lem = Lemma.objects.get(pk=pk)
    lem_uri = request.build_absolute_uri(lem.pk)
    data = lem.make_jsonld(lem_uri)
    return JsonResponse(data,safe = False)

def lemma_ttl(request, pk):
    lem = Lemma.objects.get(pk=pk)
    lem_uri = request.build_absolute_uri(lem.pk)
    data = lem.make_ttl(lem_uri)
    response = HttpResponse(content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'filename="{pk}.ttl"'

    response.write(data)

    return response

class LemmaIdView(generic.DetailView):
    model = Lemma
    template_name = "emedict/lemma_id.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["used_in"] = Lemma.objects.filter(
            components__isnull=False,
            components__pk=self.kwargs['pk']
        ).order_by("sortform")
        context["admin_edit"] = reverse(
            "admin:emedict_lemma_change", args=(self.kwargs["pk"],))
        context["emesal"] = FormType.objects.get(term="emesal")
        context["lem_search_form"] = LemmaAdvancedSearchForm
        context["lem_init_form"] = LemmaInitialLetterForm

        return context

def tags(request):
    taggedlems = Lemma.objects.filter(tags__isnull=False)
    ctags = Tag.objects.filter(type="CO", lemma__in=taggedlems).distinct().order_by("term")
    gtags = Tag.objects.filter(type="GR", lemma__in=taggedlems).distinct().order_by("term")
    stags = Tag.objects.filter(type="SO", lemma__in=taggedlems).distinct().order_by("term")
    wtags = Tag.objects.filter(type="WL", lemma__in=taggedlems).distinct().order_by("term")
    shtags = Tag.objects.filter(type="SH", lemma__in=taggedlems).distinct().order_by("term")

    context = {
        "ctags": ctags,
        "gtags": gtags,
        "stags": stags,
        "wtags": wtags,
        "shtags": shtags
        }

    return render(request, "emedict/tags_home.html", context)

class CompVerbView(generic.ListView):
    model = Lemma
    queryset = Lemma.objects.filter(
        Q(pos__term="verb") & ~Q(components=None)
    ).order_by("sortform")

    context_object_name = "lemmalist"
    template_name = "emedict/compverbs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["verbs"] = Lemma.objects.filter(
                lemma__in=self.queryset, pos__term='verb'
            ).order_by('sortform').distinct()

        context["nouns"] = Lemma.objects.filter(
                lemma__in=self.queryset, pos__term='noun'
            ).order_by('sortform').distinct()

        return context

class CompVerbComponentView(generic.ListView):
    model = Lemma
    context_object_name = "lemmalist"
    template_name = "emedict/cverbnoun.html"

    def get_queryset(self) -> QuerySet[Any]:
        return Lemma.objects.filter(
            Q(pos__term="verb")
            & Q(components__pk=self.kwargs['pk'])
        ).order_by("sortform")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["baselem"] = Lemma.objects.get(pk=self.kwargs['pk'])
        return context

class LemmaEmesalListView(generic.ListView):
    model = Lemma
    context_object_name = "lemmalist"
    template_name = "emedict/lemesal.html"
    queryset = Lemma.objects.filter(
        pos__type="COM",
        forms__in=Form.objects.filter(formtype=12)
                                    ).order_by("sortform")
    # emesalform = Form.objects.get(formtype=12)

    # def get_context_data(self, **kwargs):
    #     context = super().get_context_data(**kwargs)

    #     return context

class TxtSourceView(generic.DetailView):
    model = TxtSource
    template_name = "emedict/txtsource.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["lemmata"] = Lemma.objects.filter(
            lemmacitation__source__pk=self.kwargs['pk']
        ).order_by("sortform")

        return context

class TxtSourceListView(generic.ListView):
    model = TxtSource
    context_object_name = "txtlist"
    template_name = "txtsource_list.html"

class LemmaViewSetSerialized(viewsets.ModelViewSet):
    serializer_class = LemmaSerializer
    queryset = Lemma.objects.all()
    http_method_names = ['get', 'post', 'head']
