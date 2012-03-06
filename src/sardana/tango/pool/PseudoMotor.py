#!/usr/bin/env python

##############################################################################
##
## This file is part of Sardana
##
## http://www.tango-controls.org/static/sardana/latest/doc/html/index.html
##
## Copyright 2011 CELLS / ALBA Synchrotron, Bellaterra, Spain
## 
## Sardana is free software: you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
## 
## Sardana is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
## 
## You should have received a copy of the GNU Lesser General Public License
## along with Sardana.  If not, see <http://www.gnu.org/licenses/>.
##
##############################################################################

""" """

__all__ = ["PseudoMotor", "PseudoMotorClass"]

__docformat__ = 'restructuredtext'

import time

from PyTango import Util, DevFailed, Except, READ, READ_WRITE, SCALAR, \
    SPECTRUM, DevVoid, DevShort, DevLong, DevLong64, DevDouble, DevBoolean, \
    DevString, DevVarStringArray, DispLevel, DevState, AttrQuality, TimeVal

from taurus.core.util.log import InfoIt, DebugIt

from sardana import State, SardanaServer
from sardana.sardanaattribute import SardanaAttribute
from sardana.pool.poolexception import PoolException
from sardana.tango.core.util import to_tango_type_format, to_tango_state
from PoolDevice import PoolElementDevice, PoolElementDeviceClass


class PseudoMotor(PoolElementDevice):

    def __init__(self, dclass, name):
        PoolElementDevice.__init__(self, dclass, name)
        PseudoMotor.init_device(self)

    def init(self, name):
        PoolElementDevice.init(self, name)

    def _is_allowed(self, req_type):
        return PoolElementDevice._is_allowed(self, req_type)

    def get_pseudo_motor(self):
        return self.element

    def set_pseudo_motor(self, pseudo_motor):
        self.element = pseudo_motor

    pseudo_motor = property(get_pseudo_motor, set_pseudo_motor)
    
    @DebugIt()
    def delete_device(self):
        PoolElementDevice.delete_device(self)
    
    @DebugIt()
    def init_device(self):
        PoolElementDevice.init_device(self)

        self.Elements = map(int, self.Elements)
        if self.pseudo_motor is None:
            full_name = self.get_name()
            name = self.alias or full_name
            pseudo_motor = self.pool.create_element(type="PseudoMotor",
                name=name, full_name=full_name, id=self.Id,
                axis=self.Axis, ctrl_id=self.Ctrl_id,
                user_elements=self.Elements)
            if self.instrument is not None:
                pseudo_motor.set_instrument(self.instrument)
            pseudo_motor.add_listener(self.on_pseudo_motor_changed)
            self.pseudo_motor = pseudo_motor
        # force a state read to initialize the state attribute
        self.set_state(DevState.ON)
        
    def on_pseudo_motor_changed(self, event_source, event_type, event_value):
        # during server startup and shutdown avoid processing element
        # creation events
        if SardanaServer.server_state != State.Running:
            return

        t = time.time()
        name = event_type.name.lower()
        multi_attr = self.get_device_attr()
        attr = multi_attr.get_attr_by_name(name)
        quality = AttrQuality.ATTR_VALID
        
        recover = False
        if event_type.priority > 1 and attr.is_check_change_criteria():
            attr.set_change_event(True, False)
            recover = True
        
        try:
            if name == "state":
                state = self.calculate_tango_state(event_value)
                attr.set_value(state)
                attr.fire_change_event()
                #self.push_change_event(name, state)
            elif name == "status":
                status = self.calculate_tango_status(event_value)
                attr.set_value(status)
                attr.fire_change_event()
                #self.push_change_event(name, status)
            else:
                if isinstance(event_value, SardanaAttribute):
                    if event_value.error:
                        dev_failed = Except.to_dev_failed(*event_value.exc_info)
                        attr.fire_change_event(dev_failed)
                        return
                    t = event_value.timestamp
                    event_value = event_value.value
                
                state = self.pseudo_motor.get_state()
                
                if state == State.Moving and name == "position":
                    quality = AttrQuality.ATTR_CHANGING
                
                attr.set_value_date_quality(event_value, t, quality)
                attr.fire_change_event()
                #self.push_change_event(name, event_value, t, quality)
                
        finally:
            if recover:
                attr.set_change_event(True, True)

    def always_executed_hook(self):
        #state = to_tango_state(self.pseudo_motor.get_state(cache=False))
        pass

    def read_attr_hardware(self,data):
        pass

    def initialize_dynamic_attributes(self):
        attrs = PoolElementDevice.initialize_dynamic_attributes(self)
        
        detect_evts = "position",
        non_detect_evts = ()
            
        for attr_name in detect_evts:
            if attrs.has_key(attr_name):
                self.set_change_event(attr_name, True, True)
        for attr_name in non_detect_evts:
            if attrs.has_key(attr_name):
                self.set_change_event(attr_name, True, False)
        return
    
    def add_standard_attribute(self, attr_name, data_info, attr_info, read,
                               write, is_allowed):
        # For position attribute, listen to what the controller says for data
        # type (between long and float)
        if attr_name.lower() == 'position':
            ttype, tformat = to_tango_type_format(attr_info.get('type'))
            data_info[0][0] = ttype
        return PoolElementDevice.add_standard_attribute(self, attr_name,
            data_info, attr_info, read, write, is_allowed)
    
    def read_Position(self, attr):
        moving = self.get_state() == DevState.MOVING
        position = self.pseudo_motor.get_position(cache=moving)
        if position.error:
            Except.throw_python_exception(*position.exc_info)
        attr.set_value(position.value)
        if moving:
            attr.set_quality(AttrQuality.ATTR_CHANGING)
        attr.set_date(TimeVal.fromtimestamp(position.timestamp))
        
    def write_Position(self, attr):
        try:
            self.pseudo_motor.position = attr.get_write_value()
        except PoolException, pe:
            if pe.exc_info is None:
                raise
            Except.throw_python_exception(*pe.exc_info)
    
    def MoveRelative(self, argin):
        raise NotImplementedError
    
    def is_MoveRelative_allowed(self):
        if self.get_state() in (DevState.FAULT, DevState.MOVING, DevState.UNKNOWN):
            return False
        return True
    
    is_Position_allowed = _is_allowed


class PseudoMotorClass(PoolElementDeviceClass):

    #    Class Properties
    class_property_list = {
    }

    #    Device Properties
    device_property_list = {
        "Elements" :    [ DevVarStringArray, "elements used by the pseudo", [ ] ],
    }
    device_property_list.update(PoolElementDeviceClass.device_property_list)

    #    Command definitions
    cmd_list = {
        'MoveRelative' :   [ [DevDouble, "amount to move"], [DevVoid, ""] ],
    }
    cmd_list.update(PoolElementDeviceClass.cmd_list)

    #    Attribute definitions
    standard_attr_list = {
        'Position'     : [ [ DevDouble, SCALAR, READ_WRITE ] ],
    }
    standard_attr_list.update(PoolElementDeviceClass.standard_attr_list)

