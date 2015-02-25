# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import os.path

from aldryn_apphooks_config.mixins import AppConfigMixin
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse
from django.utils.timezone import now
from django.utils.translation import get_language
from django.views.generic import DetailView, ListView
from parler.views import TranslatableSlugMixin, ViewUrlMixin

from .models import BlogCategory, Post
from .settings import get_setting

User = get_user_model()


class AjaxListMixin(object):
    """
    A subclass of *django.views.generic.ListView* that allows AJAX
    pagination of a list of objects.

    You can use this class based view in place of *ListView* in order to
    recreate the behaviour of the *page_template* decorator.

    For instance, assume you have this code (taken from Django docs)::

        from django.conf.urls.defaults import *
        from django.views.generic import ListView
        from books.models import Publisher

        urlpatterns = patterns('',
            (r'^publishers/$', ListView.as_view(model=Publisher)),
        )

    You want to AJAX paginate publishers, so, as seen, you need to switch
    the template if the request is AJAX and put the page template
    into the context as a variable named *page_template*.

    This is straightforward, you only need to replace the view class, e.g.::

        from django.conf.urls.defaults import *
        from books.models import Publisher

        from endless_pagination.views import AjaxListView

        urlpatterns = patterns('',
            (r'^publishers/$', AjaxListView.as_view(model=Publisher)),
        )

    NOTE: Django >= 1.3 is required to use this view.
    """
    key = "page"
    page_template = None
    page_template_suffix = '_page'

    def get_page_template(self, **kwargs):
        """
        Only called if *page_template* is not given as a kwarg of
        *self.as_view*.
        """
        opts = self.object_list.model._meta
        return "%s/%s%s%s.html" % (opts.app_label, opts.object_name.lower(),
                                   self.template_name_suffix, self.page_template_suffix)

    def get_context_data(self, **kwargs):
        """
        Adds the *page_template* variable in the context.

        If the *page_template* is not given as a kwarg of the *as_view*
        method then it is invented using app label, model name
        (obviously if the list is a queryset), *self.template_name_suffix*
        and *self.page_template_suffix*.

        For instance, if the list is a queryset of *blog.Entry*,
        the template will be *blog/entry_list_page.html*.
        """
        context = super(AjaxListMixin, self).get_context_data(**kwargs)
        if self.page_template is None:
            if hasattr(self.object_list, 'model'):
                self.page_template = self.get_page_template(**kwargs)
            else:
                raise ImproperlyConfigured(
                    'AjaxListMixin requires a page_template')
        context['page_template'] = self.page_template
        return context

    def get_template_names(self):
        """
        Switch the templates for AJAX requests.
        """
        request = self.request
        querystring_key = request.REQUEST.get("querystring_key", self.key)
        if request.is_ajax() and querystring_key == self.key:
            return [self.page_template]
        return super(AjaxListMixin, self).get_template_names()


class BaseBlogView(AppConfigMixin, ViewUrlMixin):

    def get_view_url(self):
        if not self.view_url_name:
            raise ImproperlyConfigured(
                'Missing `view_url_name` attribute on {0}'.format(self.__class__.__name__)
            )

        url = reverse(
            self.view_url_name,
            args=self.args,
            kwargs=self.kwargs,
            current_app=self.namespace
        )
        return self.request.build_absolute_uri(url)

    def get_queryset(self):
        language = get_language()
        queryset = self.model._default_manager.namespace(
            self.namespace
        ).active_translations(
            language_code=language
        )
        if not getattr(self.request, 'toolbar', False) or not self.request.toolbar.edit_mode:
            queryset = queryset.published()
        setattr(self.request, get_setting('CURRENT_NAMESPACE'), self.config)
        return queryset

    def get_template_names(self):
        template_path = (self.config and self.config.template_prefix) or 'djangocms_blog'
        return os.path.join(template_path, self.base_template_name)


class PostListView(AjaxListMixin, BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    base_template_name = 'post_list.html'
    view_url_name = 'djangocms_blog:posts-latest'

    def get_context_data(self, **kwargs):
        context = super(PostListView, self).get_context_data(**kwargs)
        context['TRUNCWORDS_COUNT'] = get_setting('POSTS_LIST_TRUNCWORDS_COUNT')
        return context

    def get_paginate_by(self, queryset):
        return (self.config and self.config.paginate_by) or get_setting('PAGINATION')


class PostDetailView(TranslatableSlugMixin, BaseBlogView, DetailView):
    model = Post
    context_object_name = 'post'
    base_template_name = 'post_detail.html'
    slug_field = 'slug'
    view_url_name = 'djangocms_blog:post-detail'

    def get_queryset(self):
        queryset = self.model._default_manager.all()
        if not getattr(self.request, 'toolbar', False) or not self.request.toolbar.edit_mode:
            queryset = queryset.published()
        return queryset

    def get(self, *args, **kwargs):
        # submit object to cms to get corrent language switcher and selected category behavior
        if hasattr(self.request, 'toolbar'):
            self.request.toolbar.set_object(self.get_object())
        return super(PostDetailView, self).get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(PostDetailView, self).get_context_data(**kwargs)
        context['meta'] = self.get_object().as_meta()
        context['use_placeholder'] = get_setting('USE_PLACEHOLDER')
        setattr(self.request, get_setting('CURRENT_POST_IDENTIFIER'), self.get_object())
        return context


class PostArchiveView(AjaxListMixin, BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    base_template_name = 'post_list.html'
    date_field = 'date_published'
    allow_empty = True
    allow_future = True
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-archive'

    def get_queryset(self):
        qs = super(PostArchiveView, self).get_queryset()
        if 'month' in self.kwargs:
            qs = qs.filter(**{'%s__month' % self.date_field: self.kwargs['month']})
        if 'year' in self.kwargs:
            qs = qs.filter(**{'%s__year' % self.date_field: self.kwargs['year']})
        return qs

    def get_context_data(self, **kwargs):
        kwargs['month'] = int(self.kwargs.get('month')) if 'month' in self.kwargs else None
        kwargs['year'] = int(self.kwargs.get('year')) if 'year' in self.kwargs else None
        if kwargs['year']:
            kwargs['archive_date'] = now().replace(kwargs['year'], kwargs['month'] or 1, 1)
        context = super(PostArchiveView, self).get_context_data(**kwargs)
        context['TRUNCWORDS_COUNT'] = get_setting('POSTS_LIST_TRUNCWORDS_COUNT')
        return context


class TaggedListView(AjaxListMixin, BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    base_template_name = 'post_list.html'
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-tagged'

    def get_queryset(self):
        qs = super(TaggedListView, self).get_queryset()
        return qs.filter(tags__slug=self.kwargs['tag'])

    def get_context_data(self, **kwargs):
        if 'tag' in self.kwargs:
            tag_obj = Tag.objects.get(slug=self.kwargs['tag'])
            kwargs['tag'] = tag_obj
        kwargs['tagged_entries'] = (self.kwargs.get('tag')
                                    if 'tag' in self.kwargs else None)
        context = super(TaggedListView, self).get_context_data(**kwargs)
        context['TRUNCWORDS_COUNT'] = get_setting('POSTS_LIST_TRUNCWORDS_COUNT')
        return context


class AuthorEntriesView(AjaxListMixin, BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    base_template_name = 'post_list.html'
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-authors'

    def get_queryset(self):
        qs = super(AuthorEntriesView, self).get_queryset()
        if 'username' in self.kwargs:
            qs = qs.filter(**{'author__%s' % User.USERNAME_FIELD: self.kwargs['username']})
        return qs

    def get_context_data(self, **kwargs):
        kwargs['author'] = User.objects.get(**{User.USERNAME_FIELD: self.kwargs.get('username')})
        context = super(AuthorEntriesView, self).get_context_data(**kwargs)
        context['TRUNCWORDS_COUNT'] = get_setting('POSTS_LIST_TRUNCWORDS_COUNT')
        return context


class CategoryEntriesView(AjaxListMixin, BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    base_template_name = 'post_list.html'
    _category = None
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-category'

    @property
    def category(self):
        if not self._category:
            self._category = BlogCategory.objects.active_translations(
                get_language(), slug=self.kwargs['category']
            ).get()
        return self._category

    def get(self, *args, **kwargs):
        # submit object to cms toolbar to get correct language switcher behavior
        if hasattr(self.request, 'toolbar'):
            self.request.toolbar.set_object(self.category)
        return super(CategoryEntriesView, self).get(*args, **kwargs)

    def get_queryset(self):
        qs = super(CategoryEntriesView, self).get_queryset()
        if 'category' in self.kwargs:
            qs = qs.filter(categories=self.category.pk)
        return qs

    def get_context_data(self, **kwargs):
        kwargs['category'] = self.category
        context = super(CategoryEntriesView, self).get_context_data(**kwargs)
        context['TRUNCWORDS_COUNT'] = get_setting('POSTS_LIST_TRUNCWORDS_COUNT')
        return context

