/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License Version 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

use crate::error::MwComProviderError;
use crate::generated;
use crate::quality::SignalQuality;
use crate::transport::{MwComMessage, MwComTransport, MwComValue};
use async_trait::async_trait;
use std::mem::MaybeUninit;
use std::os::raw::{c_char, c_void};
use std::ptr::NonNull;
use std::slice;
use std::str;
use std::time::{Duration, UNIX_EPOCH};

const STATUS_OK: i32 = 0;

const VALUE_BOOL: u32 = 0;
const VALUE_STRING: u32 = 1;
const VALUE_I64: u32 = 2;
const VALUE_U64: u32 = 3;
const VALUE_F64: u32 = 4;
const VALUE_BYTES: u32 = 5;

#[repr(C)]
struct MwComNativeTransportHandle {
    _private: [u8; 0],
}

#[repr(C)]
struct MwComNativeElementConfig {
    service_name: *const c_char,
    instance_name: *const c_char,
    member_name: *const c_char,
    element_kind: *const c_char,
    payload_type: *const c_char,
    sample_size: usize,
    sample_alignment: usize,
    has_serialized_format: u8,
}

#[repr(C)]
struct MwComNativeValue {
    kind: u32,
    bool_value: u8,
    i64_value: i64,
    u64_value: u64,
    f64_value: f64,
    bytes_ptr: *const u8,
    bytes_len: usize,
}

#[repr(C)]
struct MwComNativeMessage {
    service_name: *const c_char,
    instance_name: *const c_char,
    member_name: *const c_char,
    value: MwComNativeValue,
    has_source_timestamp: u8,
    source_timestamp_nanos_since_epoch: u64,
    quality: u32,
}

extern "C" {
    fn mw_com_provider_native_create(
        elements: *const MwComNativeElementConfig,
        element_count: usize,
        out_handle: *mut *mut MwComNativeTransportHandle,
    ) -> i32;
    fn mw_com_provider_native_destroy(handle: *mut MwComNativeTransportHandle);
    fn mw_com_provider_native_connect(handle: *mut MwComNativeTransportHandle) -> i32;
    fn mw_com_provider_native_disconnect(handle: *mut MwComNativeTransportHandle) -> i32;
    fn mw_com_provider_native_subscribe(
        handle: *mut MwComNativeTransportHandle,
        service_name: *const c_char,
        instance_name: *const c_char,
        member_name: *const c_char,
    ) -> i32;
    fn mw_com_provider_native_recv(
        handle: *mut MwComNativeTransportHandle,
        timeout_ms: u32,
        out_message: *mut MwComNativeMessage,
    ) -> i32;
    fn mw_com_provider_native_release_message(
        handle: *mut MwComNativeTransportHandle,
        message: *mut MwComNativeMessage,
    );
    fn mw_com_provider_native_send_actuation(
        handle: *mut MwComNativeTransportHandle,
        message: *const MwComNativeMessage,
    ) -> i32;
}

pub struct GenericMwComNativeTransport {
    handle: NonNull<MwComNativeTransportHandle>,
    recv_timeout_ms: u32,
}

unsafe impl Send for GenericMwComNativeTransport {}
unsafe impl Sync for GenericMwComNativeTransport {}

impl GenericMwComNativeTransport {
    pub fn new_from_generated() -> Result<Self, MwComProviderError> {
        Self::new(generated::GENERATED_GENERIC_MW_COM_ELEMENTS)
    }

    pub fn new(elements: &[generated::GenericMwComElement]) -> Result<Self, MwComProviderError> {
        Self::with_recv_timeout(elements, 100)
    }

    pub fn with_recv_timeout(
        elements: &[generated::GenericMwComElement],
        recv_timeout_ms: u32,
    ) -> Result<Self, MwComProviderError> {
        let (_strings, element_configs) = build_element_configs(elements)?;
        let mut handle = std::ptr::null_mut();
        let status = unsafe {
            mw_com_provider_native_create(
                element_configs.as_ptr(),
                element_configs.len(),
                &mut handle,
            )
        };
        status_to_result(status, "create mw::com native bridge transport")?;
        let handle = NonNull::new(handle).ok_or_else(|| {
            MwComProviderError::Transport(
                "mw::com native bridge create returned a null handle".into(),
            )
        })?;
        Ok(Self {
            handle,
            recv_timeout_ms,
        })
    }

    fn handle(&self) -> *mut MwComNativeTransportHandle {
        self.handle.as_ptr()
    }
}

impl Drop for GenericMwComNativeTransport {
    fn drop(&mut self) {
        unsafe {
            mw_com_provider_native_destroy(self.handle());
        }
    }
}

#[async_trait]
impl MwComTransport for GenericMwComNativeTransport {
    async fn connect(&mut self) -> Result<(), MwComProviderError> {
        let status = unsafe { mw_com_provider_native_connect(self.handle()) };
        status_to_result(status, "connect mw::com native bridge transport")
    }

    async fn disconnect(&mut self) -> Result<(), MwComProviderError> {
        let status = unsafe { mw_com_provider_native_disconnect(self.handle()) };
        status_to_result(status, "disconnect mw::com native bridge transport")
    }

    async fn subscribe(
        &mut self,
        service: &str,
        instance: &str,
        member: &str,
    ) -> Result<(), MwComProviderError> {
        let service = NativeString::new(service, "service")?;
        let instance = NativeString::new(instance, "instance")?;
        let member = NativeString::new(member, "member")?;
        let status = unsafe {
            mw_com_provider_native_subscribe(
                self.handle(),
                service.as_ptr(),
                instance.as_ptr(),
                member.as_ptr(),
            )
        };
        status_to_result(status, "subscribe mw::com native bridge transport")
    }

    async fn recv(&mut self) -> Result<MwComMessage, MwComProviderError> {
        let mut raw_message = MaybeUninit::<MwComNativeMessage>::zeroed();
        let status = unsafe {
            mw_com_provider_native_recv(
                self.handle(),
                self.recv_timeout_ms,
                raw_message.as_mut_ptr(),
            )
        };
        status_to_result(status, "receive mw::com native bridge sample")?;
        let mut raw_message = unsafe { raw_message.assume_init() };
        let message = unsafe { message_from_native(&raw_message) };
        unsafe {
            mw_com_provider_native_release_message(self.handle(), &mut raw_message);
        }
        message
    }

    async fn send_actuation(&mut self, message: MwComMessage) -> Result<(), MwComProviderError> {
        let outbound = OutboundMessage::new(&message)?;
        let status = unsafe { mw_com_provider_native_send_actuation(self.handle(), &outbound.raw) };
        status_to_result(status, "send mw::com native bridge actuation")
    }
}

struct NativeString {
    bytes: Vec<u8>,
}

impl NativeString {
    fn new(value: &str, field: &str) -> Result<Self, MwComProviderError> {
        if value.as_bytes().contains(&0) {
            return Err(MwComProviderError::Transport(format!(
                "native bridge {field} contains an interior NUL byte"
            )));
        }
        let mut bytes = Vec::with_capacity(value.len() + 1);
        bytes.extend_from_slice(value.as_bytes());
        bytes.push(0);
        Ok(Self { bytes })
    }

    fn as_ptr(&self) -> *const c_char {
        self.bytes.as_ptr().cast()
    }
}

struct ElementStrings {
    service_name: NativeString,
    instance_name: NativeString,
    member_name: NativeString,
    element_kind: NativeString,
    payload_type: NativeString,
}

fn build_element_configs(
    elements: &[generated::GenericMwComElement],
) -> Result<(Vec<ElementStrings>, Vec<MwComNativeElementConfig>), MwComProviderError> {
    let strings = elements
        .iter()
        .map(|element| {
            Ok(ElementStrings {
                service_name: NativeString::new(element.service_name, "service_name")?,
                instance_name: NativeString::new(element.instance_name, "instance_name")?,
                member_name: NativeString::new(element.member_name, "member_name")?,
                element_kind: NativeString::new(element.element_kind, "element_kind")?,
                payload_type: NativeString::new(element.payload_type, "payload_type")?,
            })
        })
        .collect::<Result<Vec<_>, MwComProviderError>>()?;

    let configs = elements
        .iter()
        .zip(strings.iter())
        .map(|(element, strings)| MwComNativeElementConfig {
            service_name: strings.service_name.as_ptr(),
            instance_name: strings.instance_name.as_ptr(),
            member_name: strings.member_name.as_ptr(),
            element_kind: strings.element_kind.as_ptr(),
            payload_type: strings.payload_type.as_ptr(),
            sample_size: element.sample_size,
            sample_alignment: element.sample_alignment,
            has_serialized_format: u8::from(element.has_serialized_format),
        })
        .collect();

    Ok((strings, configs))
}

struct OutboundMessage {
    raw: MwComNativeMessage,
    _service_name: NativeString,
    _instance_name: NativeString,
    _member_name: NativeString,
    _bytes: Vec<u8>,
}

impl OutboundMessage {
    fn new(message: &MwComMessage) -> Result<Self, MwComProviderError> {
        let service_name = NativeString::new(&message.service, "service")?;
        let instance_name = NativeString::new(&message.instance, "instance")?;
        let member_name = NativeString::new(&message.member, "member")?;
        let (value, bytes) = value_to_native(&message.value);
        let source_timestamp_nanos_since_epoch = message
            .source_timestamp
            .and_then(|timestamp| timestamp.duration_since(UNIX_EPOCH).ok())
            .map(|duration| duration.as_nanos().min(u128::from(u64::MAX)) as u64)
            .unwrap_or(0);

        Ok(Self {
            raw: MwComNativeMessage {
                service_name: service_name.as_ptr(),
                instance_name: instance_name.as_ptr(),
                member_name: member_name.as_ptr(),
                value,
                has_source_timestamp: u8::from(message.source_timestamp.is_some()),
                source_timestamp_nanos_since_epoch,
                quality: quality_to_native(message.quality),
            },
            _service_name: service_name,
            _instance_name: instance_name,
            _member_name: member_name,
            _bytes: bytes,
        })
    }
}

fn value_to_native(value: &MwComValue) -> (MwComNativeValue, Vec<u8>) {
    match value {
        MwComValue::Bool(value) => (
            MwComNativeValue {
                kind: VALUE_BOOL,
                bool_value: u8::from(*value),
                i64_value: 0,
                u64_value: 0,
                f64_value: 0.0,
                bytes_ptr: std::ptr::null(),
                bytes_len: 0,
            },
            Vec::new(),
        ),
        MwComValue::String(value) => {
            let bytes = value.as_bytes().to_vec();
            (bytes_value(VALUE_STRING, &bytes), bytes)
        }
        MwComValue::I64(value) => (
            MwComNativeValue {
                kind: VALUE_I64,
                bool_value: 0,
                i64_value: *value,
                u64_value: 0,
                f64_value: 0.0,
                bytes_ptr: std::ptr::null(),
                bytes_len: 0,
            },
            Vec::new(),
        ),
        MwComValue::U64(value) => (
            MwComNativeValue {
                kind: VALUE_U64,
                bool_value: 0,
                i64_value: 0,
                u64_value: *value,
                f64_value: 0.0,
                bytes_ptr: std::ptr::null(),
                bytes_len: 0,
            },
            Vec::new(),
        ),
        MwComValue::F64(value) => (
            MwComNativeValue {
                kind: VALUE_F64,
                bool_value: 0,
                i64_value: 0,
                u64_value: 0,
                f64_value: *value,
                bytes_ptr: std::ptr::null(),
                bytes_len: 0,
            },
            Vec::new(),
        ),
        MwComValue::Bytes(value) => (bytes_value(VALUE_BYTES, value), value.clone()),
    }
}

fn bytes_value(kind: u32, bytes: &[u8]) -> MwComNativeValue {
    MwComNativeValue {
        kind,
        bool_value: 0,
        i64_value: 0,
        u64_value: 0,
        f64_value: 0.0,
        bytes_ptr: bytes.as_ptr(),
        bytes_len: bytes.len(),
    }
}

unsafe fn message_from_native(
    message: &MwComNativeMessage,
) -> Result<MwComMessage, MwComProviderError> {
    Ok(MwComMessage {
        service: cstr_to_string(message.service_name, "service")?,
        instance: cstr_to_string(message.instance_name, "instance")?,
        member: cstr_to_string(message.member_name, "member")?,
        value: value_from_native(&message.value)?,
        source_timestamp: if message.has_source_timestamp != 0 {
            Some(UNIX_EPOCH + Duration::from_nanos(message.source_timestamp_nanos_since_epoch))
        } else {
            None
        },
        quality: quality_from_native(message.quality)?,
    })
}

unsafe fn value_from_native(value: &MwComNativeValue) -> Result<MwComValue, MwComProviderError> {
    match value.kind {
        VALUE_BOOL => Ok(MwComValue::Bool(value.bool_value != 0)),
        VALUE_STRING => {
            let bytes = bytes_from_native(value.bytes_ptr, value.bytes_len)?;
            String::from_utf8(bytes)
                .map(MwComValue::String)
                .map_err(|error| {
                    MwComProviderError::Transport(format!("invalid native bridge string: {error}"))
                })
        }
        VALUE_I64 => Ok(MwComValue::I64(value.i64_value)),
        VALUE_U64 => Ok(MwComValue::U64(value.u64_value)),
        VALUE_F64 => Ok(MwComValue::F64(value.f64_value)),
        VALUE_BYTES => bytes_from_native(value.bytes_ptr, value.bytes_len).map(MwComValue::Bytes),
        other => Err(MwComProviderError::Transport(format!(
            "unsupported native bridge value kind {other}"
        ))),
    }
}

unsafe fn bytes_from_native(ptr: *const u8, len: usize) -> Result<Vec<u8>, MwComProviderError> {
    if ptr.is_null() && len != 0 {
        return Err(MwComProviderError::Transport(
            "native bridge value has null bytes pointer with non-zero length".into(),
        ));
    }
    Ok(if len == 0 {
        Vec::new()
    } else {
        slice::from_raw_parts(ptr, len).to_vec()
    })
}

unsafe fn cstr_to_string(ptr: *const c_char, field: &str) -> Result<String, MwComProviderError> {
    if ptr.is_null() {
        return Err(MwComProviderError::Transport(format!(
            "native bridge message has null {field} pointer"
        )));
    }
    let bytes = native_string_bytes(ptr.cast());
    str::from_utf8(bytes)
        .map(ToString::to_string)
        .map_err(|error| {
            MwComProviderError::Transport(format!("invalid native bridge {field}: {error}"))
        })
}

unsafe fn native_string_bytes<'a>(ptr: *const u8) -> &'a [u8] {
    let mut len = 0;
    while *ptr.add(len) != 0 {
        len += 1;
    }
    slice::from_raw_parts(ptr, len)
}

fn status_to_result(status: i32, operation: &str) -> Result<(), MwComProviderError> {
    if status == STATUS_OK {
        Ok(())
    } else {
        Err(MwComProviderError::Transport(format!(
            "{operation} failed with native bridge status {status}"
        )))
    }
}

fn quality_to_native(quality: SignalQuality) -> u32 {
    match quality {
        SignalQuality::Invalid => 0,
        SignalQuality::Stale => 1,
        SignalQuality::Degraded => 2,
        SignalQuality::Valid => 3,
    }
}

fn quality_from_native(quality: u32) -> Result<SignalQuality, MwComProviderError> {
    match quality {
        0 => Ok(SignalQuality::Invalid),
        1 => Ok(SignalQuality::Stale),
        2 => Ok(SignalQuality::Degraded),
        3 => Ok(SignalQuality::Valid),
        other => Err(MwComProviderError::Transport(format!(
            "unsupported native bridge signal quality {other}"
        ))),
    }
}

#[allow(dead_code)]
fn assert_opaque_handle_is_c_compatible(_: *mut c_void) {}
