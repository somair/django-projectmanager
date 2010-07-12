from django.db import models
import datetime, decimal
from string_utils import smart_truncate
from django.http import HttpResponseRedirect
from django.db.models.signals import pre_save, post_save, post_init
from django.contrib.auth.models import User
from django.db.models import Q, Sum
import settings as pm_settings
import calendar

class ForUserManager(models.Manager):
    def for_user(self, user):
        return self.get_query_set().filter(Q(users=user) | Q(owner=user))
        
        
# Create your models here.
class Project(models.Model):
    owner = models.ForeignKey(User, related_name='project_ownership_set')
    users = models.ManyToManyField(User, related_name='project_membership_set', blank=True)
    client = models.CharField(max_length=200, blank=True)
    name = models.CharField(max_length=200)
    slug = models.CharField(max_length=60, unique=True)
    description = models.TextField(blank=True)
    completed = models.BooleanField()
    billable = models.BooleanField(default=1)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=80)
    creation_date = models.DateTimeField(auto_now_add=True)
    billing_type = models.CharField(max_length=5, choices=(('quote', 'Quote'), ('time', 'Time'),), default='quote')
    
    objects = ForUserManager()
    
    def __unicode__(self):
        if self.client:
            return "%s, %s" % (self.client, self.name)
        else:
            return self.name
    
    def pending_task_count(self):
        return self.task_set.filter(completed=False).count()
    
    def total_time(self):
        delta = sum((item.total_time() for item in ProjectTime.objects.filter(project=self.id)), datetime.timedelta())
        return (delta.days * 24 + delta.seconds / 3600) + (((0.0 + delta.seconds / 60) % 60) / 60)
    
    def total_estimated_hours(self, completed=False):
        tasks = self.task_set.all()
        if completed:
            tasks = tasks.filter(completed=True)
        return tasks.aggregate(Sum('estimated_hours'))['estimated_hours__sum'] or ''
    
    """
    def time_invoiced(self):
        time = sum((invoice.hours for invoice in InvoiceRow.objects.filter(project=self.id)))
        return float(time)#"%d:%d" % (time.floor(), ((time - time.floor()) * 60 / 100))
    """
    
    def total_expenses(self):
        return float(sum(item.amount for item in ProjectExpense.objects.filter(project=self.id)))
        
    def time_invoiced(self):
        return float(sum(item.quantity for item in InvoiceRow.objects.filter(project=self) if item.is_time))
        
    def total_invoiced(self):
        return float(sum(item.amount() for item in InvoiceRow.objects.filter(project=self)))
        
    def total_cost(self):
        if self.billing_type == 'quote':
            return self.total_expenses() + float(self.total_estimated_hours(True) or 0) * float(self.hourly_rate)
        else:
            return self.total_expenses() + self.total_time() * float(self.hourly_rate)
    
    def total_to_invoice(self):
        return self.total_cost() - self.total_invoiced()
    
    def approx_hours_to_invoice(self):
        if self.hourly_rate:
            return str(round(int(self.total_to_invoice() * 4) / self.hourly_rate) / 4)
        else:
            return ''
    
    def create_invoice(self):
        times = self.projecttime_set.all()
        expenses = self.projectexpense_set.all()
        try:
            last_invoice_date = Invoice.objects.filter(projects=self).order_by('-creation_date')[0].creation_date
            times = times.filter(creation_date__gte=last_invoice_date)
            expenses = expenses.filter(creation_date__gte=last_invoice_date)
        except IndexError:
            pass
        
        new_invoice = Invoice.objects.create(client=self.client, description=self.name)
        """
        print times
        for time in times:
            InvoiceRow.objects.create(
                invoice=new_invoice,
                project=time.project,
                detail=project.name,
                quantity=int(time.total_time()),
                price=time.project.hourly_rate,
            )
        """
        return new_invoice
    
    @models.permalink
    def projecttime_summary_url(self):
        return ('projectmanager.views.projecttime_summary', (self.pk, ), )
    
    class Meta:
        ordering = ('client', 'name',)

    

class ForProjectUserManager(models.Manager):
    def for_user(self, user):
        return self.get_query_set().filter(Q(project__users=user) | Q(project__owner=user))
        


class ProjectTime(models.Model):
    creation_date = models.DateTimeField(auto_now_add=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    description = models.TextField()
    project = models.ForeignKey(Project)
    _time = models.DecimalField(max_digits=4, decimal_places=2, null=True, editable=False)

    objects = ForProjectUserManager()

    
    def description_truncated(self):
        return smart_truncate(self.description, 100)
    
    def __unicode__(self):
        return "%s: %s (%s)" % (self.project.name, self.description, unicode(self.start))
    
    def total_time(self):
        return (self.end - self.start)
    
    def get_absolute_url(self):
        return "/time/%s-%s-%s/" % (self.start.year, self.start.month, self.start.day)
    
    def save(self, force_insert=False, force_update=False):
        self.start = round_datetime(self.start)
        self.end = round_datetime(self.end)
        
        self._time = str((self.total_time().days * 24 + self.total_time().seconds / 3600) + (((0.0 + self.total_time().seconds / 60) % 60) / 60))

        super(ProjectTime, self).save(force_insert, force_update)


def round_datetime(dt):
    return dt + datetime.timedelta(minutes=(round(float(dt.minute + float(dt.second) / 60) / 15) * 15 - dt.minute), seconds=-dt.second)
    
class ProjectExpense(models.Model):
    creation_date = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    project = models.ForeignKey(Project)


    objects = ForProjectUserManager()

    
    def description_truncated(self):
        return smart_truncate(self.description, 30)
    
    def __unicode__(self):
        return "%s: %s (%s)" % (self.project.name, self.description, self.amount)
    


class Invoice(models.Model):
    creation_date = models.DateTimeField(auto_now_add=True)
    client = models.CharField(max_length=255)
    email = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    paid = models.BooleanField()
    projects = models.ManyToManyField(Project, through="InvoiceRow")

    objects = ForProjectUserManager()

    
    def pdf_filename(self):
        return "Invoice %s - %s - %s.pdf" % (self.creation_date.strftime("%Y-%m-%d"), self.client, self.description)
    
    def __unicode__(self):
        return self.address

    def subtotal(self):
        return sum(item.amount() for item in InvoiceRow.objects.filter(invoice=self))
    
    def gst_amount(self):
        return round(float(self.subtotal()) * 0.125, 2)
    
    def total(self):
        return round(float(self.subtotal()) * 1.125, 2)
    
    @models.permalink
    def get_absolute_url(self):
        return ('projectmanager.views.invoice', [self.pk])



def create_invoice_for_projects(project_qs):
    new_invoice = Invoice.objects.create(client=project_qs.all()[0].client)
    for project in project_qs.all():
        InvoiceRow.objects.create(
            invoice=new_invoice,
            project=project,
            detail=project.name,
            quantity=project.approx_hours_to_invoice(),
            price=project.hourly_rate,
        )
        
    
    return new_invoice
    

"""
INVOICE_ROW_TYPES = (
    ('hours', 'Hours'),
    ('expenses', 'Expenses'),
)
"""

class InvoiceRow(models.Model):
    project = models.ForeignKey(Project)
    invoice = models.ForeignKey(Invoice)
    detail = models.CharField(max_length=255, blank=True)
    #type = models.CharField(max_length=255, choices=INVOICE_ROW_TYPES)
    #project_expense = models.ForeignKey(ProjectExpense, limit_choices_to={'invoicerow': None})
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    #amount = models.DecimalField(max_digits=10, decimal_places=2)

    def amount(self):
        return self.price * self.quantity

    def __unicode__(self):
        return "%s on %s" % (self.amount(), self.project.name)
        
    
    # assume its time if the rate is the same as the project rate - dubious yes, maybe
    # this should be a db field populated on creation?
    @property
    def is_time(self):
        return (self.price == self.project.hourly_rate)

    def invoice_date(self):
        return datetime.date(self.invoice.creation_date.year, self.invoice.creation_date.month, self.invoice.creation_date.day)


class Task(models.Model):
    project = models.ForeignKey(Project)
    task =  models.TextField()
    comments = models.TextField(blank=True)
    completed = models.BooleanField()
    creation_date = models.DateTimeField(auto_now_add=True)
    completion_date = models.DateTimeField(null=True, editable=False)
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    objects = ForProjectUserManager()
    
    
    @models.permalink
    def get_absolute_url(self):
        return ('projectmanager.views.tasks',)
    
    def __unicode__(self):
        return "%s (%s)" % (self.task, self.project.name)
    
    class Meta:
        ordering = ('creation_date',)
    
def set_completion_date(sender, **kwargs):
    if kwargs['instance'].completed and not kwargs['instance'].completion_date:
        kwargs['instance'].completion_date = datetime.datetime.now()
pre_save.connect(set_completion_date, sender=Task)



class HostingClient(models.Model):
    owner = models.ForeignKey(User, related_name='hostingclient_ownership_set', default=1)
    users = models.ManyToManyField(User, related_name='hostingclient_membership_set', blank=True)
    client = models.CharField(max_length=200, blank=True)
    name = models.CharField(max_length=200)
    slug = models.CharField(max_length=60, unique=True)
    billing_frequency = models.CharField(u'billing type', editable=False, max_length=10, choices=pm_settings.BILLING_PERIOD_MONTHS_CHOICES, default=pm_settings.BILLING_PERIOD_MONTHS_DEFAULT)
    billing_period = models.CharField(max_length=10, editable=False, default='month')
    period_fee = models.DecimalField(max_digits=10, decimal_places=2, default=25)
    start_date = models.DateField(default=datetime.date.today)
    invoice_rows = models.ManyToManyField(InvoiceRow, through='HostingInvoiceRow')
    
    invoice_due = models.BooleanField(db_column='invoice_due', editable=False)
    
    def _invoice_due(self):
        #print (self.total_paid < self.total_cost), (self.total_paid, self.total_cost)
        return (self.total_paid() <= self.total_cost())
    
    
    def total_cost(self):
        months = datetime.date.today().month - self.start_date.month + (datetime.date.today().year - self.start_date.year) * 12
        return months * self.period_fee
    
    def total_paid(self):
        return sum(r.amount() for r in self.invoice_rows.filter(invoice__paid=True))

    def total_invoiced(self):
        return sum(r.amount() for r in self.invoice_rows.all())

    def __unicode__(self):
        return "%s - %s" % (self.client, self.name)
    

def hostingclient_prefill(sender, *args, **kwargs):
    if kwargs['instance'].pk:
        kwargs['instance'].invoice_due = kwargs['instance']._invoice_due()
pre_save.connect(hostingclient_prefill, sender=HostingClient)
post_init.connect(hostingclient_prefill, sender=HostingClient)

class HostingInvoiceRow(models.Model):
    hostingclient = models.ForeignKey(HostingClient)
    invoicerow = models.ForeignKey(InvoiceRow)
    
    def __unicode__(self):
        return "%s, %s: $%s" % (self.hostingclient.client, self.hostingclient.name, self.invoicerow.amount())
        


def create_invoice_for_hosting_clients(hostingclient_qs):
    invoice_list = []
    for hostingclient in hostingclient_qs.all():
        new_invoice = Invoice.objects.create(client=hostingclient.client, description="Website hosting")
        
        periods_invoiced = HostingInvoiceRow.objects.filter(hostingclient=hostingclient).aggregate(models.Sum('invoicerow__quantity'))['invoicerow__quantity__sum']
        periods_to_invoice = periods_invoiced + decimal.Decimal(hostingclient.billing_frequency)
        
        year = int(hostingclient.start_date.year + int(hostingclient.start_date.month + periods_to_invoice) / 12)
        month = int((hostingclient.start_date.month + periods_to_invoice) % 12)
        day = min(hostingclient.start_date.day, calendar.monthrange(year, month)[1])
        
        
        new_row = InvoiceRow.objects.create(
            invoice=new_invoice,
            project=Project.objects.get(slug='hosting'),
            detail='Website hosting until %s/%s/%s' % (day, month, year),
            quantity=hostingclient.billing_frequency,
            price=hostingclient.period_fee,
        )
        
        HostingInvoiceRow.objects.create(invoicerow=new_row, hostingclient=hostingclient)
        invoice_list.append(new_invoice)
    
    return invoice_list
    