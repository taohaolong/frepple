#
# Copyright (C) 2007-2013 by frePPLe bvba
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from datetime import timedelta, datetime

from django.db import connections
from django.db.models.expressions import RawSQL
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import string_concat

from freppledb.boot import getAttributeFields
from freppledb.input.models import Buffer, Item, Location, OperationPlanMaterial
from freppledb.common.report import GridPivot, GridFieldText, GridFieldNumber, GridFieldLastModified


class OverviewReport(GridPivot):
  '''
  A report showing the inventory profile of buffers.
  '''
  template = 'output/buffer.html'
  title = _('Inventory report')

  @classmethod
  def basequeryset(reportclass, request, *args, **kwargs):
    if len(args) and args[0]:
      return Buffer.objects.all()
    else:
      return OperationPlanMaterial.objects.values('item', 'location') \
        .order_by('item_id', 'location_id') \
        .distinct() \
        .annotate(
          buffer=RawSQL("item_id || ' @ ' || location_id", ())
          )

  model = OperationPlanMaterial
  default_sort = (1, 'asc', 2, 'asc')
  permissions = (('view_inventory_report', 'Can view inventory report'),)
  help_url = 'user-guide/user-interface/plan-analysis/inventory-report.html'

  rows = (
    GridFieldText('buffer', title=_('buffer'), editable=False, key=True, initially_hidden=True),
    GridFieldText('item', title=_('item'), editable=False, field_name='item__name', formatter='detail', extra='"role":"input/item"'),
    GridFieldText('location', title=_('location'), editable=False, field_name='location__name', formatter='detail', extra='"role":"input/location"'),
    # Optional fields referencing the item
    GridFieldText('item__description', title=string_concat(_('item'), ' - ', _('description')),
      initially_hidden=True, editable=False),
    GridFieldText('item__category', title=string_concat(_('item'), ' - ', _('category')),
      initially_hidden=True, editable=False),
    GridFieldText('item__subcategory', title=string_concat(_('item'), ' - ', _('subcategory')),
      initially_hidden=True, editable=False),
    GridFieldNumber('item__cost', title=string_concat(_('item'), ' - ', _('cost')),
      initially_hidden=True, editable=False),
    GridFieldText('item__owner', title=string_concat(_('item'), ' - ', _('owner')),
      field_name='item__owner__name', initially_hidden=True, editable=False),
    GridFieldText('item__source', title=string_concat(_('item'), ' - ', _('source')),
      initially_hidden=True, editable=False),
    GridFieldLastModified('item__lastmodified', title=string_concat(_('item'), ' - ', _('last modified')),
      initially_hidden=True, editable=False),
    # Optional fields referencing the location
    GridFieldText('location__description', title=string_concat(_('location'), ' - ', _('description')),
      initially_hidden=True, editable=False),
    GridFieldText('location__category', title=string_concat(_('location'), ' - ', _('category')),
      initially_hidden=True, editable=False),
    GridFieldText('location__subcategory', title=string_concat(_('location'), ' - ', _('subcategory')),
      initially_hidden=True, editable=False),
    GridFieldText('location__available', title=string_concat(_('location'), ' - ', _('available')),
      initially_hidden=True, field_name='origin__available__name', formatter='detail',
      extra='"role":"input/calendar"', editable=False),
    GridFieldText('location__owner', title=string_concat(_('location'), ' - ', _('owner')),
      initially_hidden=True, field_name='origin__owner__name', formatter='detail',
      extra='"role":"input/location"', editable=False),
    GridFieldText('location__source', title=string_concat(_('location'), ' - ', _('source')),
      initially_hidden=True, editable=False),
    GridFieldLastModified('location__lastmodified', title=string_concat(_('location'), ' - ', _('last modified')),
      initially_hidden=True, editable=False),
    )

  crosses = (
    ('startoh', {'title': _('start inventory')}),
    ('startohdoc', {'title': _('start inventory days of cover')}),
    ('safetystock', {'title': _('safety stock')}),
    ('consumed', {'title': _('total consumed')}),
    ('consumedMO', {'title': _('consumed by MO')}),
    ('consumedDO', {'title': _('consumed by DO')}),
    ('consumedSO', {'title': _('consumed by SO')}),
    ('produced', {'title': _('total produced')}),
    ('producedMO', {'title': _('produced by MO')}),
    ('producedDO', {'title': _('produced by DO')}),
    ('producedPO', {'title': _('produced by PO')}),
    ('endoh', {'title': _('end inventory')}),
    ('total_in_progress', {'title': _('total in progress')}),
    ('work_in_progress_mo', {'title': _('work in progress MO')}),
    ('on_order_po', {'title': _('on order PO')}),
    ('in_transit_do', {'title': _('in transit DO')}),
    )


  @classmethod
  def initialize(reportclass, request):
    if reportclass._attributes_added != 2:
      reportclass._attributes_added = 2
      reportclass.attr_sql = ''
      # Adding custom item attributes
      for f in getAttributeFields(Item, initially_hidden=True):
        reportclass.rows += (f,)
        reportclass.attr_sql += 'item.%s, ' % f.name.split('__')[-1]
      # Adding custom location attributes
      for f in getAttributeFields(Location, related_name_prefix="location", initially_hidden=True):
        reportclass.rows += (f,)
        reportclass.attr_sql += 'location.%s, ' % f.name.split('__')[-1]

  @classmethod
  def extra_context(reportclass, request, *args, **kwargs):
    if args and args[0]:
      request.session['lasttab'] = 'plan'
      return {
        'title': force_text(Buffer._meta.verbose_name) + " " + args[0],
        'post_title': _('plan')
        }
    else:
      return {}

  @classmethod
  def query(reportclass, request, basequery, sortsql='1 asc'):
    cursor = connections[request.database].cursor()
    basesql, baseparams = basequery.query.get_compiler(basequery.db).as_sql(with_col_aliases=False)

    # Execute the actual query
    query = '''
       select item.name||' @ '||location.name,
       item.name item_id,
       location.name location_id,
       item.description,
       item.category,
       item.subcategory,
       item.cost,
       item.owner_id,
       item.source,
       item.lastmodified,
       location.description,
       location.category,
       location.subcategory,
       location.available_id,
       location.owner_id,
       location.source,
       location.lastmodified,
       %s
       (select jsonb_build_object('onhand', onhand, 'flowdate', to_char(flowdate,'YYYY-MM-DD HH24:MI:SS'), 'periodofcover', periodofcover) 
       from operationplanmaterial where item_id = item.name and
       location_id = location.name and flowdate < greatest(d.startdate,%%s)
       order by flowdate desc, id desc limit 1) startoh,
       d.bucket,
       d.startdate,
       d.enddate,
       (select safetystock from
        (
        select 1 as priority, coalesce((select value from calendarbucket 
        where calendar_id = 'SS for '||item.name||' @ '||location.name
        and greatest(d.startdate,%%s) >= startdate and greatest(d.startdate,%%s) < enddate
        order by priority limit 1), (select defaultvalue from calendar where name = 'SS for '||item.name||' @ '||location.name)) as safetystock
        union all
        select 2 as priority, coalesce((select value from calendarbucket 
        where calendar_id = (select minimum_calendar_id from buffer where name = item.name||' @ '||location.name)
        and greatest(d.startdate,%%s) >= startdate and greatest(d.startdate,%%s) < enddate
        order by priority limit 1), (select defaultvalue from calendar where name = (select minimum_calendar_id from buffer where name = item.name||' @ '||location.name))) as safetystock
        union all
        select 3 as priority, minimum as safetystock from buffer where name = item.name||' @ '||location.name
        ) t
        where t.safetystock is not null
        order by priority
        limit 1) safetystock,
       (select jsonb_build_object(
      'work_in_progress_mo', sum(case when (startdate < d.enddate and enddate >= d.enddate) and opm.quantity > 0 and operationplan.type = 'MO' then opm.quantity else 0 end),
      'on_order_po', sum(case when (startdate < d.enddate and enddate >= d.enddate) and opm.quantity > 0 and operationplan.type = 'PO' then opm.quantity else 0 end),
      'in_transit_do', sum(case when (startdate < d.enddate and enddate >= d.enddate) and opm.quantity > 0 and operationplan.type = 'DO' then opm.quantity else 0 end),
      'total_in_progress', sum(case when (startdate < d.enddate and enddate >= d.enddate) and opm.quantity > 0 then opm.quantity else 0 end),
      'consumed', sum(case when (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity < 0 then -opm.quantity else 0 end),
      'consumedMO', sum(case when operationplan.type = 'MO' and (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity < 0 then -opm.quantity else 0 end),
      'consumedDO', sum(case when operationplan.type = 'DO' and (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity < 0 then -opm.quantity else 0 end),
      'consumedSO', sum(case when operationplan.type = 'DLVR' and (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity < 0 then -opm.quantity else 0 end),
      'produced', sum(case when (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity > 0 then opm.quantity else 0 end),
      'producedMO', sum(case when operationplan.type = 'MO' and (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity > 0 then opm.quantity else 0 end),
      'producedDO', sum(case when operationplan.type = 'DO' and (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity > 0 then opm.quantity else 0 end),
      'producedPO', sum(case when operationplan.type = 'PO' and (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate) and opm.quantity > 0 then opm.quantity else 0 end)
      )
      from operationplanmaterial opm
      inner join operationplan on operationplan.reference = opm.operationplan_id 
      and ((startdate < d.enddate and enddate >= d.enddate) 
            or (opm.flowdate >= greatest(d.startdate,%%s) and opm.flowdate < d.enddate))
      where opm.item_id = item.name and opm.location_id = location.name) ongoing
       from
       (%s) opplanmat
       inner join item on item.name = opplanmat.item_id
       inner join location on location.name = opplanmat.location_id
       -- Multiply with buckets
      cross join (
         select name as bucket, startdate, enddate
         from common_bucketdetail
         where bucket_id = %%s and enddate > %%s and startdate < %%s
         ) d
      group by
       item.name,
       location.name,
       item.description, 
       item.category, 
       item.subcategory,
       item.cost,
       item.owner_id,
       item.source, 
       item.lastmodified, 
       location.description, 
       location.category,
       location.subcategory, 
       location.available_id, 
       location.owner_id,
       location.source, 
       location.lastmodified,
       d.bucket,
       d.startdate,
       d.enddate
       order by %s, d.startdate
    ''' % (
        reportclass.attr_sql, basesql, sortsql
      )

    # Build the python result
    with connections[request.database].chunked_cursor() as cursor_chunked:
      cursor_chunked.execute(
        query,
        (
          request.report_startdate,  # startoh
          request.report_startdate, request.report_startdate, request.report_startdate, request.report_startdate,  # safetystock
        ) +
        (request.report_startdate, ) * 9 +  # ongoing
        baseparams +  # opplanmat
        (request.report_bucket, request.report_startdate, request.report_enddate),  # bucket d
        )
      for row in cursor_chunked:
        numfields = len(row)
        res = {
          'buffer': row[0],
          'item': row[1],
          'location': row[2],
          'item__description': row[3],
          'item__category': row[4],
          'item__cost': row[6],
          'item__owner': row[7],
          'item__source': row[8],
          'item__lastmodified': row[9],
          'location__description': row[10],
          'location__category': row[11],
          'location__subcategory': row[12],
          'location__available_id': row[13],
          'location__owner_id': row[14],
          'location__source': row[15],
          'location__lastmodified': row[16],
          'startoh': row[numfields - 6]['onhand'] if row[numfields - 6] else 0,
          'startohdoc': 0 if (row[numfields - 6]['onhand']  if row[numfields - 6] else 0) <= 0\
                          else (999 if row[numfields - 6]['periodofcover'] == 86313600\
                                    else (datetime.strptime(row[numfields - 6]['flowdate'],'%Y-%m-%d %H:%M:%S') +\
                                          timedelta(seconds=row[numfields - 6]['periodofcover']) - row[numfields - 4]).days if row[numfields - 6]['periodofcover'] else 999),
          'bucket': row[numfields - 5],
          'startdate': row[numfields - 4].date(),
          'enddate': row[numfields - 3].date(),
          'safetystock': row[numfields - 2] or 0,
          'consumed': row[numfields - 1]['consumed'] or 0,
          'consumedMO': row[numfields - 1]['consumedMO'] or 0,
          'consumedDO': row[numfields - 1]['consumedDO'] or 0,
          'consumedSO': row[numfields - 1]['consumedSO'] or 0,
          'produced': row[numfields - 1]['produced'] or 0,
          'producedMO': row[numfields - 1]['producedMO'] or 0,
          'producedDO': row[numfields - 1]['producedDO'] or 0,
          'producedPO': row[numfields - 1]['producedPO'] or 0,
          'total_in_progress': row[numfields - 1]['total_in_progress'] or 0,
          'work_in_progress_mo': row[numfields - 1]['work_in_progress_mo'] or 0,
          'on_order_po': row[numfields - 1]['on_order_po'] or 0,
          'in_transit_do': row[numfields - 1]['in_transit_do'] or 0,
          'endoh': float(row[numfields - 6]['onhand'] if row[numfields - 6] else 0) + float(row[numfields - 1]['produced'] or 0) - float(row[numfields - 1]['consumed'] or 0),
          }
        # Add attribute fields
        idx = 16
        for f in getAttributeFields(Item, related_name_prefix="item"):
          res[f.field_name] = row[idx]
          idx += 1
        for f in getAttributeFields(Location, related_name_prefix="location"):
          res[f.field_name] = row[idx]
          idx += 1
        yield res
