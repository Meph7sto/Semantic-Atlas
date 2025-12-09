from flask import Blueprint, request, jsonify
from .services import RequirementAnalysisService
from .models import Requirement, TraceRecord, Risk, Suggestion
from . import db

api_bp = Blueprint('api', __name__)
analysis_service = RequirementAnalysisService()

@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'service': '需求追溯系统',
        'version': '1.0.0'
    })


@api_bp.route('/trace-relation', methods=['POST'])
def trace_requirement_relation():
    """基于顶层需求和底层需求进行追溯关系分析"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '请提供分析数据'
            }), 400
        
        high_level_req = data.get('high_level_requirement', '').strip()
        low_level_req = data.get('low_level_requirement', '').strip()
        
        if not high_level_req or not low_level_req:
            return jsonify({
                'success': False,
                'error': '请提供顶层需求和底层需求'
            }), 400
        
        # 使用需求分析服务进行关系判断
        analysis_result = analysis_service.analyze_requirement_relation(high_level_req, low_level_req)
        
        # 可选：保存到数据库
        save_to_db = data.get('save_to_db', False)
        if save_to_db:
            try:
                analysis_service.save_trace_relation_to_db(high_level_req, low_level_req, analysis_result)
            except Exception as e:
                print(f"保存到数据库失败: {e}")
        
        return jsonify({
            'success': True,
            'data': analysis_result
        })
        
    except Exception as e:
        print(f"需求关系分析失败: {e}")
        return jsonify({
            'success': False,
            'error': '需求关系分析服务暂时不可用，请稍后重试'
        }), 500

@api_bp.route('/batch-trace-relation', methods=['POST'])
def batch_trace_requirement_relation():
    """批量分析多对顶层需求和底层需求的追溯关系"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '请提供分析数据'
            }), 400
        
        high_level_requirements = data.get('high_level_requirements', [])
        low_level_requirements = data.get('low_level_requirements', [])
        
        if not high_level_requirements or not low_level_requirements:
            return jsonify({
                'success': False,
                'error': '请提供顶层需求列表和底层需求列表'
            }), 400
        
        # 使用需求分析服务进行批量关系分析
        batch_result = analysis_service.batch_analyze_requirement_relations(
            high_level_requirements, low_level_requirements
        )
        
        # 可选：保存到数据库
        save_to_db = data.get('save_to_db', False)
        if save_to_db:
            try:
                analysis_service.save_batch_trace_relations_to_db(batch_result)
            except Exception as e:
                print(f"批量保存到数据库失败: {e}")
        
        return jsonify({
            'success': True,
            'data': batch_result
        })
        
    except Exception as e:
        print(f"批量需求关系分析失败: {e}")
        return jsonify({
            'success': False,
            'error': '批量需求关系分析服务暂时不可用，请稍后重试'
        }), 500

@api_bp.route('/requirements', methods=['GET'])
def get_requirements():
    """获取所有需求列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        requirements = Requirement.query.order_by(Requirement.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'success': True,
            'data': {
                'requirements': [req.to_dict() for req in requirements.items],
                'total': requirements.total,
                'pages': requirements.pages,
                'current_page': page
            }
        })
        
    except Exception as e:
        print(f"获取需求列表失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取需求列表失败'
        }), 500

@api_bp.route('/requirements/<int:requirement_id>', methods=['GET'])
def get_requirement_detail(requirement_id):
    """获取需求详情和追溯链"""
    try:
        requirement = Requirement.query.get_or_404(requirement_id)
        
        # 获取追溯记录
        trace_records = TraceRecord.query.filter_by(requirement_id=requirement_id).all()
        
        # 获取风险记录
        risks = Risk.query.filter_by(requirement_id=requirement_id).all()
        
        # 获取建议记录
        suggestions = Suggestion.query.filter_by(requirement_id=requirement_id).all()
        
        return jsonify({
            'success': True,
            'data': {
                'requirement': requirement.to_dict(),
                'traceAnalysis': [record.to_dict() for record in trace_records],
                'risks': [risk.to_dict() for risk in risks],
                'suggestions': [suggestion.to_dict() for suggestion in suggestions]
            }
        })
        
    except Exception as e:
        print(f"获取需求详情失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取需求详情失败'
        }), 500

@api_bp.route('/requirements/<int:requirement_id>', methods=['DELETE'])
def delete_requirement(requirement_id):
    """删除需求"""
    try:
        requirement = Requirement.query.get_or_404(requirement_id)
        db.session.delete(requirement)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '需求删除成功'
        })
        
    except Exception as e:
        print(f"删除需求失败: {e}")
        return jsonify({
            'success': False,
            'error': '删除需求失败'
        }), 500

@api_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """获取统计数据"""
    try:
        total_requirements = Requirement.query.count()
        total_traces = TraceRecord.query.count()
        total_risks = Risk.query.count()
        
        # 按类型统计追溯记录
        trace_stats = db.session.query(
            TraceRecord.stage_type,
            db.func.count(TraceRecord.id)
        ).group_by(TraceRecord.stage_type).all()
        
        # 按风险等级统计
        risk_stats = db.session.query(
            Risk.level,
            db.func.count(Risk.id)
        ).group_by(Risk.level).all()
        
        return jsonify({
            'success': True,
            'data': {
                'total_requirements': total_requirements,
                'total_traces': total_traces,
                'total_risks': total_risks,
                'trace_type_stats': dict(trace_stats),
                'risk_level_stats': dict(risk_stats)
            }
        })
        
    except Exception as e:
        print(f"获取统计数据失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取统计数据失败'
        }), 500

@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': '资源未找到'
    }), 404

@api_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500
