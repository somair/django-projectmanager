$(document).ready(function() {

  var date = new Date();
	var d = date.getDate();
	var m = date.getMonth();
	var y = date.getFullYear();
	
	var calendar = $('#calendar').fullCalendar({
		header: {
			left: 'prev,next today',
			center: 'title',
			//right: 'month,basicWeek,basicDay'
			right: 'month,agendaWeek,agendaDay'
		},
		editable: true,
		firstHour: 8,
		defaultView: 'agendaWeek',
		//contentHeight: 1500,
		firstDay: 1, // monday
		events: "/api/time/list/",
		loading: onCalendarLoading,
		select: onCalendarSelect,
		eventDrop: onCalendarEventUpdate,
		eventResize: onCalendarEventUpdate,
		eventClick: onCalendarEventClick,
		selectable: true,
		selectHelper: true,
		slotMinutes: 15
	});

	$("form.addtime").submit(onTimeFormSubmit);
	$("#add_time_cancel, #add_time_overlay").click(hideAddTimeForm);

	$(document).keydown(onDocumentKeyDown)


	function onCalendarLoading(bool)
	{
			if (bool) $('#loading').show();
			else $('#loading').hide();
	};

	function onCalendarSelect(start, end, allDay)
	{
		// Prefill the form.
		$('form.addtime #id_id').val('0');
		$('#add_time #id_start').val(formatDate(start));
		$('#add_time #id_end').val(formatDate(end));
		$('#add_time #id_description').val("");
		$('#add_time #id_project').focus();
		$("#add_time, #add_time_overlay").fadeIn(300);
		$('#add_time .delete').hide();
		alert('hello');
	};

	function onCalendarEventUpdate(event, delta)
	{
		_jQueryPost("/api/time/move/", _eventToPostVars(event), null);
	};

	function onCalendarEventClick(event)
	{
		// Prefill the form.
		$('form.addtime #id_id').val(event._id);
		$('#add_time #id_start').val(formatDate(event.start));
		$('#add_time #id_end').val(formatDate(event.end));
		$('#add_time #id_project').val(event._project_id);
		$('#add_time #id_description').val(event._description).focus();
		$("#add_time, #add_time_overlay").fadeIn(300);
		$('#add_time .delete').show().attr('href', $('#add_time .delete').attr('href').replace('/0/', '/' + event._id + '/'));
		alert('hello 2');
	};

	function onTimeFormSubmit(event)
	{
		event.preventDefault();
		var form = $("form.addtime");

		if( !parseInt(form[0].elements['id'].value) )
			_jQueryPost("/api/time/add/", $("form.addtime").serialize(), onAddTimeResponse);
		else
			_jQueryPost("/api/time/edit/", $("form.addtime").serialize(), onEditTimeResponse);
	};

	function onAddTimeResponse(data, status, xhr)
	{
		if( ! data.status )
		{
			displayFormErrors(data.errors);
			return;
		}

		calendar.fullCalendar('renderEvent', data.event, true); // third arg makes make the event "stick"
		hideAddTimeForm();  // hides the selection band.
	};

	function onEditTimeResponse(data, status, xhr)
	{
		if( ! data.status )
		{
			displayFormErrors(data.errors);
			return;
		}

		// Update the existing item with the new values.
		var newevent = calendar.fullCalendar('clientEvents', data.event._id)[0];
		for(var prop in data.event)
			newevent[prop] = data.event[prop];

		calendar.fullCalendar('updateEvent', newevent);
		hideAddTimeForm();  // hides the selection band.
	};

	function onAjaxError()
	{
		alert("Server error, unable to update database!");
	};

	function onDocumentKeyDown(event)
	{
		if( event.which == 27 ) {  // escape
			hideAddTimeForm();
		}
	};

	function displayFormErrors(errors)
	{
		var msg = '';
		for( var fieldname in errors )
			msg += fieldname + ": " + errors[fieldname];
		alert(msg);
	};


	function hideAddTimeForm()
	{
		$("#add_time, #add_time_overlay").fadeOut(500);
		calendar.fullCalendar('unselect');
	};

	function formatDate(date)
	{
		// JavaScript has no native format function.
		var hours = date.getHours().toString();
		var mins = date.getMinutes().toString();
		if( hours.length == 1 ) hours = "0" + hours;
		if( mins.length == 1 ) mins = "0" + mins;
		return date.getFullYear() + "-" + (date.getMonth()+1) + "-" + date.getDate() + " " + hours + ":" + mins;
	};


	// ---- Ajax posting ----

	function _jQueryPost(url, postdata, onsuccess)
	{
		jQuery.ajax(url, {
			'type': 'POST',
			'data': postdata,
			'dataType': 'json',
			'success': onsuccess,
			'error': onAjaxError
		});
	};

	function _eventToPostVars(event)
	{
		var postvars = {
			'id': event._id,
			'title': event.title,
			'start': formatDate(event.start),
			'end': formatDate(event.end),
			'allDay': event.allDay
		};
		if( event._project_id )
			postvars['project_id'] = event._project_id;
		return jQuery.param(postvars);
	};

});