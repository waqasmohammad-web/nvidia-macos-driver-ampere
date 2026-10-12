//! Deliberately bounded CPU executor for the buffer regressions below. Unsupported
//! instructions and missing memory fail loudly; this is not a GPU implementation.
use super::*;
use crate::spirv_module::Instruction;

#[derive(Clone, Debug)]
enum Value {
    Scalar(u64),
    Pointer {
        set: u32,
        binding: u32,
        offset: u64,
        pointee: Word,
    },
}

#[derive(Default)]
pub(super) struct Memory(pub HashMap<(u32, u32, u64), u8>);
const PHYSICAL: u32 = u32::MAX;
impl Memory {
    pub fn put(&mut self, set: u32, binding: u32, offset: u64, bits: u64, bytes: u32) {
        for i in 0..bytes {
            self.0.insert(
                (set, binding, offset + u64::from(i)),
                (bits >> (8 * i)) as u8,
            );
        }
    }
    pub fn physical(&mut self, address: u64, bits: u64, bytes: u32) {
        self.put(PHYSICAL, 0, address, bits, bytes);
    }
    pub fn get(&self, set: u32, binding: u32, offset: u64, bytes: u32) -> u64 {
        (0..bytes).fold(0, |bits, i| {
            bits | (u64::from(
                *self
                    .0
                    .get(&(set, binding, offset + u64::from(i)))
                    .expect("regression executor read unspecified memory"),
            ) << (8 * i))
        })
    }
}

struct Executor<'a> {
    module: &'a Module,
    defs: HashMap<Word, &'a Instruction>,
    globals: HashMap<Word, Value>,
    memory: &'a mut Memory,
    steps: usize,
}
impl<'a> Executor<'a> {
    fn literal(op: &Operand) -> u32 {
        if let Operand::LiteralBit32(v) = op {
            *v
        } else {
            panic!("expected literal: {op:?}")
        }
    }
    fn id(op: &Operand) -> Word {
        if let Operand::IdRef(v) = op {
            *v
        } else {
            panic!("expected id: {op:?}")
        }
    }
    fn scalar(value: &Value) -> u64 {
        if let Value::Scalar(v) = value {
            *v
        } else {
            panic!("expected scalar: {value:?}")
        }
    }
    fn decoration(&self, id: Word, kind: Decoration) -> u32 {
        self.module
            .annotations
            .iter()
            .find_map(|i| {
                (i.class.opcode == Op::Decorate
                    && i.operands.first() == Some(&Operand::IdRef(id))
                    && i.operands.get(1) == Some(&Operand::Decoration(kind)))
                .then(|| Self::literal(&i.operands[2]))
            })
            .expect("required layout decoration")
    }
    fn pointee(&self, ty: Word) -> Word {
        Self::id(&self.defs[&ty].operands[1])
    }
    fn width(&self, ty: Word) -> u32 {
        Self::literal(&self.defs[&ty].operands[0])
    }
    fn size(&self, ty: Word) -> u64 {
        let i = self.defs[&ty];
        match i.class.opcode {
            Op::TypeInt | Op::TypeFloat => u64::from(self.width(ty) / 8),
            Op::TypeVector => {
                self.size(Self::id(&i.operands[0])) * u64::from(Self::literal(&i.operands[1]))
            }
            _ => panic!("unsupported executor size: {i:?}"),
        }
    }
    fn call(&mut self, function: Word, args: Vec<Value>) -> Option<Value> {
        let f = self
            .module
            .functions
            .iter()
            .find(|f| f.def.as_ref().and_then(|i| i.result_id) == Some(function))
            .expect("function");
        assert_eq!(f.parameters.len(), args.len());
        let mut values = self.globals.clone();
        for (param, arg) in f.parameters.iter().zip(args) {
            values.insert(param.result_id.unwrap(), arg);
        }
        let mut label = f.blocks[0].label.as_ref().unwrap().result_id.unwrap();
        let mut previous = 0;
        loop {
            let block = f
                .blocks
                .iter()
                .find(|b| b.label.as_ref().and_then(|i| i.result_id) == Some(label))
                .expect("block");
            let mut next = None;
            // Read all phi inputs before publishing any of this block's phis.
            let phis = block
                .instructions
                .iter()
                .filter(|i| i.class.opcode == Op::Phi)
                .map(|i| {
                    let pair = i
                        .operands
                        .chunks_exact(2)
                        .find(|p| Self::id(&p[1]) == previous)
                        .expect("phi edge");
                    (i.result_id.unwrap(), values[&Self::id(&pair[0])].clone())
                })
                .collect::<Vec<_>>();
            values.extend(phis);
            for i in &block.instructions {
                self.steps += 1;
                assert!(self.steps < 10000, "executor step bound");
                let value = |n: usize| values[&Self::id(&i.operands[n])].clone();
                let scalar = |n: usize| Self::scalar(&value(n));
                let result = match i.class.opcode {
                    Op::Phi | Op::SelectionMerge | Op::LoopMerge => None,
                    Op::Branch => {
                        next = Some(Self::id(&i.operands[0]));
                        break;
                    }
                    Op::BranchConditional => {
                        next = Some(Self::id(&i.operands[if scalar(0) != 0 { 1 } else { 2 }]));
                        break;
                    }
                    Op::Return => return None,
                    Op::ReturnValue => return Some(value(0)),
                    Op::CopyObject | Op::Bitcast | Op::UConvert => Some(value(0)),
                    Op::IAdd => Some(Value::Scalar(scalar(0).wrapping_add(scalar(1)))),
                    Op::IMul => Some(Value::Scalar(scalar(0).wrapping_mul(scalar(1)))),
                    Op::ISub => Some(Value::Scalar(scalar(0).wrapping_sub(scalar(1)))),
                    Op::ShiftLeftLogical => Some(Value::Scalar(scalar(0) << scalar(1))),
                    Op::ShiftRightLogical => Some(Value::Scalar(scalar(0) >> scalar(1))),
                    Op::BitwiseOr => Some(Value::Scalar(scalar(0) | scalar(1))),
                    Op::BitwiseAnd => Some(Value::Scalar(scalar(0) & scalar(1))),
                    Op::IEqual => Some(Value::Scalar(u64::from(scalar(0) == scalar(1)))),
                    Op::INotEqual => Some(Value::Scalar(u64::from(scalar(0) != scalar(1)))),
                    Op::Select => Some(value(if scalar(0) != 0 { 1 } else { 2 })),
                    Op::ConvertUToPtr => Some(Value::Pointer {
                        set: PHYSICAL,
                        binding: 0,
                        offset: scalar(0),
                        pointee: self.pointee(i.result_type.unwrap()),
                    }),
                    Op::AccessChain | Op::InBoundsAccessChain => {
                        let Value::Pointer {
                            set,
                            binding,
                            mut offset,
                            mut pointee,
                        } = value(0)
                        else {
                            panic!("chain base");
                        };
                        for operand in &i.operands[1..] {
                            let index = Self::scalar(&values[&Self::id(operand)]);
                            let ty = self.defs[&pointee];
                            match ty.class.opcode {
                                Op::TypeStruct => {
                                    let member = u32::try_from(index).unwrap();
                                    let member_offset = self
                                        .module
                                        .annotations
                                        .iter()
                                        .find_map(|d| {
                                            (d.class.opcode == Op::MemberDecorate
                                                && d.operands.first()
                                                    == Some(&Operand::IdRef(pointee))
                                                && d.operands.get(1)
                                                    == Some(&Operand::LiteralBit32(member))
                                                && d.operands.get(2)
                                                    == Some(&Operand::Decoration(
                                                        Decoration::Offset,
                                                    )))
                                            .then(|| Self::literal(&d.operands[3]))
                                        })
                                        .expect("member offset");
                                    offset += u64::from(member_offset);
                                    pointee = Self::id(&ty.operands[index as usize]);
                                }
                                Op::TypeArray | Op::TypeRuntimeArray => {
                                    offset += index
                                        * u64::from(
                                            self.decoration(pointee, Decoration::ArrayStride),
                                        );
                                    pointee = Self::id(&ty.operands[0]);
                                }
                                Op::TypeVector => {
                                    pointee = Self::id(&ty.operands[0]);
                                    offset += index * self.size(pointee);
                                }
                                _ => panic!("unsupported access chain type: {ty:?}"),
                            }
                        }
                        Some(Value::Pointer {
                            set,
                            binding,
                            offset,
                            pointee,
                        })
                    }
                    Op::Load => {
                        let Value::Pointer {
                            set,
                            binding,
                            offset,
                            ..
                        } = value(0)
                        else {
                            panic!("load pointer");
                        };
                        Some(Value::Scalar(self.memory.get(
                            set,
                            binding,
                            offset,
                            self.size(i.result_type.unwrap()) as u32,
                        )))
                    }
                    Op::Store => {
                        let Value::Pointer {
                            set,
                            binding,
                            offset,
                            pointee,
                        } = value(0)
                        else {
                            panic!("store pointer");
                        };
                        self.memory
                            .put(set, binding, offset, scalar(1), self.size(pointee) as u32);
                        None
                    }
                    Op::FunctionCall => self.call(
                        Self::id(&i.operands[0]),
                        i.operands[1..]
                            .iter()
                            .map(|o| values[&Self::id(o)].clone())
                            .collect(),
                    ),
                    _ => panic!("unsupported executor instruction: {i:?}"),
                };
                if let Some(mut result) = result {
                    if let (Value::Scalar(bits), Some(ty)) = (&mut result, i.result_type) {
                        if self.defs[&ty].class.opcode == Op::TypeInt && self.width(ty) < 64 {
                            *bits &= (1u64 << self.width(ty)) - 1;
                        }
                    }
                    values.insert(i.result_id.unwrap(), result);
                }
            }
            previous = label;
            label = next.expect("block terminator");
        }
    }
}

pub(super) fn execute(module: &Module, memory: &mut Memory) {
    let mut exec = Executor {
        module,
        defs: module
            .all_inst_iter()
            .filter_map(|i| Some((i.result_id?, i)))
            .collect(),
        globals: HashMap::new(),
        memory,
        steps: 0,
    };
    for i in &module.types_global_values {
        let Some(id) = i.result_id else {
            continue;
        };
        let value = match i.class.opcode {
            Op::Constant | Op::SpecConstant => Some(Value::Scalar(match i.operands.as_slice() {
                [Operand::LiteralBit32(v)] => u64::from(*v),
                [Operand::LiteralBit64(v)] => *v,
                _ => panic!("constant: {i:?}"),
            })),
            Op::ConstantNull | Op::ConstantFalse => Some(Value::Scalar(0)),
            Op::ConstantTrue => Some(Value::Scalar(1)),
            Op::Variable => Some(Value::Pointer {
                set: exec.decoration(id, Decoration::DescriptorSet),
                binding: exec.decoration(id, Decoration::Binding),
                offset: 0,
                pointee: exec.pointee(i.result_type.unwrap()),
            }),
            _ => None,
        };
        if let Some(value) = value {
            exec.globals.insert(id, value);
        }
    }
    let entry = Executor::id(&module.entry_points[0].operands[1]);
    exec.call(entry, vec![]);
}

pub(super) fn bytes(module: &Module) -> Vec<u8> {
    module
        .assemble()
        .iter()
        .flat_map(|w| w.to_le_bytes())
        .collect()
}
